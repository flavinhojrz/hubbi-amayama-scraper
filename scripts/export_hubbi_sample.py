"""Exporta uma amostra representativa dos dados Volkswagen já coletados em
`amayama.db` para o padrão final CSV da Hubbi (exports/hubbi_volkswagen_sample.csv).

Somente leitura do banco (não modifica amayama.db). Parseia as páginas
GROUP_DETAIL já ACCEPTED (raw HTML em amayama_raw/) com o parser real do
projeto (parsing/group_detail.py) para extrair OEM/descrição/posição/
quantidade — esses dados não existem em forma estruturada no banco, só no
HTML bruto capturado.

Uso: uv run python scripts/export_hubbi_sample.py
"""

from __future__ import annotations

import contextlib
import csv
import hashlib
import io
import json
import re
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from amayama_scraper.parsing.group_detail import parse_group_detail  # noqa: E402

DB_PATH = ROOT / "amayama.db"
OUT_PATH = ROOT / "exports" / "hubbi_volkswagen_sample.csv"
IMAGES_DIR = ROOT / "exports" / "images"

HUBBI_COLUMNS = [
    "manufacturer_ref",
    "search_ref",
    "name",
    "brand",
    "application",
    "position",
    "ncm",
    "barcode",
    "gross_weight",
    "net_weight",
    "width",
    "depth",
    "height",
    "born_at",
    "deprecated_at",
    "similarity",
    "notes",
    "catalog_id",
    "file_high",
    "file_medium",
    "file_low",
    "file_water_mark",
    # Colunas extras (fora do padrão Hubbi de 22 colunas, pedidos
    # explícitos 2026-09-10): `file_high` é a imagem sem marcação (link
    # real da fonte). `image_part_number` é o rótulo em texto do número
    # no diagrama que identifica esta peça.
    #
    # A versão MARCADA (quadradinho verde sobre o número) é salva em
    # exports/images_marked/{brand}/{search_ref}-{n}.jpeg — padrão de
    # nomenclatura Hubbi (pasta=marca, arquivo=código-índice). SÓ o nome
    # do arquivo (sem a pasta, já coberta pela coluna `brand`) entra no
    # CSV em `marked_image_filename` — nunca o caminho local completo
    # (não é um link válido no destino final; quem for subir usa o
    # arquivo direto dessa pasta, mantendo o mesmo nome).
]

# Modelos VW BR priorizados pelo Tech Lead, todos com volume real de
# GROUP_DETAIL ACCEPTED (levantado via inspeção prévia do banco).
TARGET_MODELS = [
    ("AMAROK", "AMA-BR"),
    ("GOL", "GL-BR"),
    ("SAVEIRO", "SA-BR"),
    ("FOX", "FO-BR"),
    ("GOLF", "GO-BR"),
    ("BORA", "BO-BR"),
    ("CC", "CC-BR"),
    ("EOS", "EOS-BR"),
]

SPECS_PER_MODEL = 4
CATEGORIES_PER_SPEC = 4
PARTS_PER_GROUP = 2


# Algumas páginas (não só as muito antigas — confirmado em specs de vários
# anos) têm `.entriesTable__description` com uma anotação de data de
# validade colada como texto literal, ex. "... D >> - 21.08.2016" ou
# "... D - 01.09.1998>> - 31.05.2002" — não é bug do parser (confirmado
# inspecionando o HTML bruto: o texto já vem assim do site, fora de
# qualquer nested table). Como isso viola a regra do padrão Hubbi de `name`
# "sem aplicação embutida" e não há como remover com segurança sem
# arriscar cortar texto legítimo, essas linhas são descartadas da amostra
# em vez de reescritas (nunca inventar/alterar o que a fonte deu).
_DATE_CONTAMINATION = re.compile(r"\d{2}\.\d{2}\.\d{4}")

# ``position_pnc`` (o atributo ``data-key`` do Amayama) Ã© um identificador
# tÃ©cnico da ilustraÃ§Ã£o, nÃ£o uma posiÃ§Ã£o fÃ­sica. A posiÃ§Ã£o Hubbi sÃ³ Ã©
# preenchida quando hÃ¡ evidÃªncia textual explÃ­cita na descriÃ§Ã£o/detalhes.
_POSITION_COMPOUND_PATTERNS = (
    (
        re.compile(r"\bfront\s*(?:-|/|\s)\s*left\b|\bleft\s*(?:-|/|\s)\s*front\b"),
        "DIANTEIRO ESQUERDO",
    ),
    (
        re.compile(r"\bfront\s*(?:-|/|\s)\s*right\b|\bright\s*(?:-|/|\s)\s*front\b"),
        "DIANTEIRO DIREITO",
    ),
    (
        re.compile(r"\brear\s*(?:-|/|\s)\s*left\b|\bleft\s*(?:-|/|\s)\s*rear\b"),
        "TRASEIRO ESQUERDO",
    ),
    (
        re.compile(r"\brear\s*(?:-|/|\s)\s*right\b|\bright\s*(?:-|/|\s)\s*rear\b"),
        "TRASEIRO DIREITO",
    ),
)
_POSITION_SIDE_PATTERNS = (
    (re.compile(r"\b(?:left[- ]hand|lh)\b"), "ESQUERDO"),
    (re.compile(r"\b(?:right[- ]hand|rh)\b"), "DIREITO"),
    (re.compile(r"\bleft\b"), "ESQUERDO"),
    (re.compile(r"\bright\b"), "DIREITO"),
)
_POSITION_FRONT_REAR = (
    (re.compile(r"\bfront\b(?!\s+of\b)"), "DIANTEIRO"),
    (re.compile(r"\brear\b"), "TRASEIRO"),
)
_POSITION_INNER_OUTER = (
    (
        re.compile(r"\binner\s+(?:door|panel|side|seal|trim|actuator|surface|part|section|area|handle)\b"),
        "INTERNO",
    ),
    (
        re.compile(r"\bouter\s+(?:door|panel|side|seal|trim|surface|ring|joint|housing|part|section)\b"),
        "EXTERNO",
    ),
)


def derive_vehicle_position(description: str | None, details: str | None = None) -> str:
    """Derive a physical vehicle position only from explicit source text."""
    text = " ".join(value.strip() for value in (description, details) if value).lower()
    if not text:
        return ""
    for pattern, value in _POSITION_COMPOUND_PATTERNS:
        if pattern.search(text):
            return value
    for pattern, value in _POSITION_SIDE_PATTERNS:
        if pattern.search(text):
            return value
    for pattern, value in _POSITION_FRONT_REAR:
        if pattern.search(text):
            return value
    for pattern, value in _POSITION_INNER_OUTER:
        if pattern.search(text):
            return value
    return ""

# Nem todo image_url é uma imagem real da peça: quando o schema não tem
# diagrama próprio, o site ainda assim serve um placeholder genérico de
# "sem imagem" a partir de um domínio/path diferente (visto na amostra:
# https://www.amayama.com/i/catalogs/honda_gen21_en_un.png — não é a peça,
# é um "no image available" reaproveitado). Imagens reais de peça sempre
# vêm de vag-img.amayama.com/VW/Bilder/... — só essas viram file_high.
_REAL_PART_IMAGE_HOST = "https://vag-img.amayama.com/"

# A página real tem um <map>/<area> por número mostrado no diagrama (mesmo
# mecanismo que o site usa pro hover interativo): cada <area data-key=...
# title="..."> tem o MESMO data-key do <tr> da tabela de peças, e `title`
# é exatamente o rótulo numérico mostrado no desenho ("1", "(1)", "2"...)
# — dado real, nunca inferido. Pedido explícito (2026-09-10): a imagem
# salva fica sem nenhuma marcação; esse rótulo vai numa coluna própria.
def parse_area_labels(html: str) -> dict[str, str]:
    """-> position_pnc -> rótulo numérico do diagrama (`<area title=...>`)."""
    soup = BeautifulSoup(html, "lxml")
    labels: dict[str, str] = {}
    for area in soup.select("map area[data-key][title]"):
        labels[str(area["data-key"])] = str(area["title"])
    return labels


_image_download_cache: dict[str, bytes | None] = {}


def _download_image_bytes(url: str) -> bytes | None:
    if url in _image_download_cache:
        return _image_download_cache[url]
    cached_path = plain_image_path(url)
    if cached_path.exists():
        try:
            content = cached_path.read_bytes()
            Image.open(io.BytesIO(content)).verify()
            _image_download_cache[url] = content
            return content
        except Exception:
            pass
    content: bytes | None
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        Image.open(io.BytesIO(resp.content)).verify()  # só confirma que é uma imagem decodificável
        content = resp.content
    except Exception:
        content = None
    _image_download_cache[url] = content
    return content


def save_plain_image(image_url: str) -> Path | None:
    """Baixa e salva a imagem EXATAMENTE como a fonte serve — sem nenhuma
    marcação/recorte/recodificação — dedup por URL (o mesmo diagrama é
    compartilhado por várias peças do mesmo schema)."""
    out_path = plain_image_path(image_url)
    if out_path.exists():
        return out_path
    content = _download_image_bytes(image_url)
    if content is None:
        return None
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(content)
    return out_path


def plain_image_path(image_url: str) -> Path:
    digest = hashlib.sha1(image_url.encode()).hexdigest()[:16]
    return IMAGES_DIR / f"{digest}.png"


# --- Segunda imagem, com um quadradinho verde claro sobre o número ---
# Pedido explícito (2026-09-10): ter as duas — a original (`file_high`,
# link real) e uma versão marcada, salva em exports/images_marked/ mas
# SEM entrar no CSV (caminho local não é um link válido no destino final
# — quem for subir usa o arquivo direto). Reaproveita o `<map>/<area
# coords="x1,y1,x2,y2">` de cada posição (mesmo mecanismo do hover
# interativo do site). Tentativa de pegar a marcação pronta direto da
# página da peça (`?sid=...`, ver conversa) não deu: aquele overlay verde
# só existe depois do JS da página rodar — o HTML puro que dá pra buscar
# sem navegador (`requests`) não traz `data-coords`/`schema-marker` em
# lugar nenhum (confirmado, 2026-09-10). Ficou como estava: coordenadas
# do `<area>` do grupo + nosso próprio discriminador de escala.
_AreaCoords = tuple[int, int, int, int]
MARKED_IMAGES_DIR = ROOT / "exports" / "images_marked"


def parse_area_geometry(
    html: str,
) -> tuple[dict[str, _AreaCoords], dict[str, tuple[int, int]]]:
    """-> (position_pnc -> (x1,y1,x2,y2), schema_id -> (declared_width, declared_height))."""
    soup = BeautifulSoup(html, "lxml")
    areas: dict[str, _AreaCoords] = {}
    declared_sizes: dict[str, tuple[int, int]] = {}

    for schema_tag in soup.select(".epcSchema__schema[data-id]"):
        schema_id = str(schema_tag.get("data-id"))
        img = schema_tag.select_one("img.imgMap[src]")
        if img is not None and img.get("width") and img.get("height"):
            with contextlib.suppress(ValueError):
                declared_sizes[schema_id] = (int(img["width"]), int(img["height"]))
        for area in schema_tag.select("map area[data-key][coords]"):
            data_key = str(area["data-key"])
            try:
                x1, y1, x2, y2 = (int(v) for v in str(area["coords"]).split(","))
            except ValueError:
                continue
            areas[data_key] = (x1, y1, x2, y2)

    return areas, declared_sizes


def _center_dark_fill(image: Image.Image, bbox: tuple[float, float, float, float]) -> float:
    """Fração de pixels escuros só na metade central do bbox — um dígito
    real preenche o CENTRO da sua própria bbox; uma linha do desenho só
    cruzando o bbox por acaso tende a tocar as bordas, não o centro."""
    x1, y1, x2, y2 = bbox
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    w, h = (x2 - x1) * 0.5, (y2 - y1) * 0.5
    x1i, y1i = int(cx - w / 2), int(cy - h / 2)
    x2i, y2i = int(cx + w / 2), int(cy + h / 2)
    if x2i <= x1i or y2i <= y1i:
        return 0.0
    crop = image.crop((x1i, y1i, x2i, y2i)).convert("L")
    dark = sum(crop.histogram()[:150])
    return dark / (crop.width * crop.height)


def _decoded_base_image(image_url: str) -> Image.Image | None:
    content = _download_image_bytes(image_url)
    if content is None:
        return None
    try:
        return Image.open(io.BytesIO(content)).convert("RGB")
    except Exception:
        return None


# Padrão de nomenclatura Hubbi (pedido explícito, 2026-09-10): pasta =
# marca, arquivo = "{código_da_peça}-{índice}.jpeg" (índice sempre
# presente, começa em 0 mesmo quando só existe uma imagem — ex.
# "VALEO99-0.jpeg"). Registro por (brand, search_ref) garante índice
# sequencial estável e reaproveita o MESMO arquivo/índice quando duas
# linhas com o mesmo search_ref apontam pro mesmo diagrama+posição
# (nunca gera arquivo duplicado à toa).
_marked_filename_registry: dict[tuple[str, str], list[tuple[str, _AreaCoords]]] = {}


def marked_image_path(brand: str, search_ref: str, image_url: str, coords: _AreaCoords) -> Path:
    seen = _marked_filename_registry.setdefault((brand, search_ref), [])
    identity = (image_url, coords)
    index = seen.index(identity) if identity in seen else len(seen)
    if index == len(seen):
        seen.append(identity)
    return MARKED_IMAGES_DIR / brand / f"{search_ref}-{index}.jpeg"


def make_marked_diagram(
    *, image_url: str, coords: _AreaCoords, declared_size: tuple[int, int] | None, out_path: Path
) -> bool:
    """Desenha um quadradinho verde claro e translúcido em volta do número
    que identifica esta peça — mesmo estilo do marcador que o próprio site
    usa na página da peça (`rgba(0, 255, 0, 0.4)`)."""
    if out_path.exists():
        return True

    base = _decoded_base_image(image_url)
    if base is None:
        return False

    x1, y1, x2, y2 = coords

    def _scaled_bbox(sx: float, sy: float) -> tuple[float, float, float, float]:
        ax1, ax2 = sorted((x1 * sx, x2 * sx))
        ay1, ay2 = sorted((y1 * sy, y2 * sy))
        return ax1, ay1, ax2, ay2

    def _in_bounds(bbox: tuple[float, float, float, float]) -> bool:
        bx1, by1, bx2, by2 = bbox
        return bx1 >= 0 and by1 >= 0 and bx2 <= base.width and by2 <= base.height

    # A fonte usa DUAS convenções de coordenada entre páginas — em
    # algumas, `coords` já é resolução nativa da imagem (escala 1:1); em
    # outras, é relativa ao `<img width/height>` EXIBIDO (bem menor),
    # exigindo escalar por native/declared. Sem sinal estrutural confiável
    # pra saber qual vale em cada página — tenta as duas e usa
    # `_center_dark_fill` pra escolher qual realmente aponta pro traço de
    # um número (evidência real, 2026-09-10, verificado visualmente).
    candidates = []
    unscaled = _scaled_bbox(1.0, 1.0)
    if _in_bounds(unscaled):
        candidates.append(unscaled)
    if declared_size and declared_size[0] > 0 and declared_size[1] > 0:
        scaled = _scaled_bbox(base.width / declared_size[0], base.height / declared_size[1])
        if _in_bounds(scaled) and scaled not in candidates:
            candidates.append(scaled)
    if not candidates:
        return False

    best_bbox, best_score = max(
        ((bbox, _center_dark_fill(base, bbox)) for bbox in candidates), key=lambda item: item[1]
    )
    MIN_CONFIDENCE = 0.05
    if best_score < MIN_CONFIDENCE:
        return False  # nem candidato bate com "isto parece um dígito" — não arriscar
    x1, y1, x2, y2 = best_bbox

    margin_x = max((x2 - x1) * 0.35, 4)
    margin_y = max((y2 - y1) * 0.35, 4)
    bx1 = max(int(x1 - margin_x), 0)
    by1 = max(int(y1 - margin_y), 0)
    bx2 = min(int(x2 + margin_x) + 1, base.width)
    by2 = min(int(y2 + margin_y) + 1, base.height)
    if bx2 <= bx1 or by2 <= by1:
        return False

    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    ImageDraw.Draw(overlay).rectangle((bx1, by1, bx2, by2), fill=(0, 255, 0, 102))
    annotated = Image.alpha_composite(base.convert("RGBA"), overlay).convert("RGB")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    annotated.save(out_path, format="JPEG", quality=90)
    return True


def normalize_search_ref(raw: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]", "", raw).upper()
    stripped = cleaned.lstrip("0")
    return stripped or cleaned


def year_of(iso_date: str | None) -> str:
    if not iso_date:
        return ""
    return iso_date[:4]


def load_html(conn: sqlite3.Connection, raw_capture_id: str) -> str | None:
    row = conn.execute(
        """
        SELECT rb.storage_path
        FROM raw_capture rc
        JOIN raw_blob rb ON rb.content_hash = rc.content_hash
        WHERE rc.capture_id = ?
        """,
        (raw_capture_id,),
    ).fetchone()
    if row is None:
        return None
    path = ROOT / row["storage_path"]
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8", errors="replace")


def pick_specs(conn: sqlite3.Connection, vehicle_model: str, market: str) -> list[sqlite3.Row]:
    rows = conn.execute(
        """
        SELECT DISTINCT s.stable_key, s.model_code, s.amayama_catalog_id,
               s.production_period_raw, s.production_start, s.production_end,
               s.grade, s.configuration
        FROM spec_registry s
        JOIN checkpoint_entry ce ON ce.spec_key = s.stable_key AND ce.status = 'ACCEPTED'
        WHERE s.manufacturer = 'VOLKSWAGEN' AND s.vehicle_model = ? AND s.market = ?
        ORDER BY s.production_start ASC, s.model_code ASC
        """,
        (vehicle_model, market),
    ).fetchall()
    if not rows:
        return []
    if len(rows) <= SPECS_PER_MODEL:
        return list(rows)
    step = len(rows) / SPECS_PER_MODEL
    return [rows[int(i * step)] for i in range(SPECS_PER_MODEL)]


def pick_categories(conn: sqlite3.Connection, spec_key: str) -> list[str]:
    rows = conn.execute(
        """
        SELECT DISTINCT category_slug FROM checkpoint_entry
        WHERE spec_key = ? AND status = 'ACCEPTED'
        ORDER BY category_slug ASC
        """,
        (spec_key,),
    ).fetchall()
    slugs = [r["category_slug"] for r in rows]
    if not slugs:
        return []
    if len(slugs) <= CATEGORIES_PER_SPEC:
        return slugs
    step = len(slugs) / CATEGORIES_PER_SPEC
    return [slugs[int(i * step)] for i in range(CATEGORIES_PER_SPEC)]


def pick_group(conn: sqlite3.Connection, spec_key: str, category_slug: str) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT group_id, raw_capture_id FROM checkpoint_entry
        WHERE spec_key = ? AND category_slug = ? AND status = 'ACCEPTED'
        ORDER BY group_id ASC LIMIT 1
        """,
        (spec_key, category_slug),
    ).fetchone()


def build_row(
    *,
    vehicle_model: str,
    spec: sqlite3.Row,
    category_slug: str,
    group_id: str,
    schema_id: str,
    part,
    area_coords: dict[str, _AreaCoords],
    declared_sizes: dict[str, tuple[int, int]],
    materialize_images: bool = True,
) -> dict[str, str] | None:
    if not part.oem_code or not part.description:
        return None  # obrigatório ausente — não inventar, descartar a linha
    if _DATE_CONTAMINATION.search(part.description):
        return None  # descrição contaminada com data de validade — ver comentário acima

    start_year = year_of(spec["production_start"])
    end_year = year_of(spec["production_end"])
    period = f"{start_year}/{end_year}" if end_year else start_year
    application_parts = [f"VOLKSWAGEN {vehicle_model}", spec["model_code"], period]
    if spec["grade"]:
        application_parts.append(f"grade={spec['grade']}")
    if spec["configuration"]:
        application_parts.append(f"configuration={spec['configuration']}")
    application = " - ".join(part for part in application_parts if part).strip(" -")

    notes_parts = [
        f"category={category_slug}",
        f"group={group_id}",
        f"schema={schema_id}",
    ]
    if part.quantity:
        notes_parts.append(f"qty={part.quantity}")
    if part.details:
        notes_parts.append(f"details={part.details}")
    if spec["grade"]:
        notes_parts.append(f"grade={spec['grade']}")
    if spec["configuration"]:
        notes_parts.append(f"configuration={spec['configuration']}")
    if spec["production_period_raw"]:
        notes_parts.append(f"production_period={spec['production_period_raw']}")

    is_real_image = bool(part.image_url) and part.image_url.startswith(_REAL_PART_IMAGE_HOST)
    # file_high é o link real da imagem na fonte (Tech Lead abre fora deste
    # repo) — nunca um caminho local. A imagem também é salva em
    # exports/images/ (save_plain_image) só como cópia de referência/backup,
    # não é o que entra no CSV.
    file_high = part.image_url if is_real_image else ""
    brand = "VOLKSWAGEN"
    search_ref = normalize_search_ref(part.oem_code)

    # Gera e salva a versão marcada (quadradinho verde) já no padrão de
    # nomenclatura Hubbi: exports/images_marked/{brand}/{search_ref}-{n}.jpeg
    # — pedido explícito 2026-09-10, ver marked_image_path(). O nome do
    # arquivo (sem a pasta da marca, que já é a própria coluna `brand`)
    # entra no CSV pra cada linha apontar pro arquivo certo depois do
    # upload.
    coords = area_coords.get(part.position_pnc) if part.position_pnc else None
    if is_real_image and coords is not None and materialize_images:
        out_path = marked_image_path(brand, search_ref, part.image_url, coords)
        if not out_path.exists():
            save_plain_image(part.image_url)
        make_marked_diagram(
            image_url=part.image_url,
            coords=coords,
            declared_size=declared_sizes.get(schema_id),
            out_path=out_path,
        )

    return {
        "manufacturer_ref": part.oem_code,
        "search_ref": search_ref,
        "name": part.description,
        "brand": brand,
        "application": application,
        "position": derive_vehicle_position(part.description, part.details),
        "ncm": "",
        "barcode": "",
        "gross_weight": "",
        "net_weight": "",
        "width": "",
        "depth": "",
        "height": "",
        "born_at": start_year,
        "deprecated_at": end_year,
        "similarity": "[]",
        "notes": "; ".join(notes_parts),
        "catalog_id": spec["amayama_catalog_id"] or "",
        "file_high": file_high,
        "file_medium": "",
        "file_low": "",
        "file_water_mark": "",
    }


def main() -> None:
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row

    rows: list[dict[str, str]] = []
    # dedup key: (model, spec, category, group, schema+position)
    seen_keys: set[tuple[str, str, str, str, str]] = set()

    def add_group(vehicle_model: str, spec: sqlite3.Row, category_slug: str, group_id: str) -> int:
        entry = conn.execute(
            "SELECT raw_capture_id FROM checkpoint_entry "
            "WHERE spec_key=? AND category_slug=? AND group_id=? AND status='ACCEPTED'",
            (spec["stable_key"], category_slug, group_id),
        ).fetchone()
        if entry is None:
            return 0
        html = load_html(conn, entry["raw_capture_id"])
        if html is None:
            return 0
        parsed = parse_group_detail(html, category_slug=category_slug, group_id=group_id)
        if parsed.critical_error is not None:
            return 0  # nunca usar página que falhou estruturalmente
        area_coords, declared_sizes = parse_area_geometry(html)

        added = 0
        for schema in parsed.schemas:
            for part in schema.parts[:PARTS_PER_GROUP]:
                dedup_key = (
                    vehicle_model,
                    spec["stable_key"],
                    category_slug,
                    group_id,
                    part.position_pnc,
                )
                if dedup_key in seen_keys:
                    continue
                row = build_row(
                    vehicle_model=vehicle_model,
                    spec=spec,
                    category_slug=category_slug,
                    group_id=group_id,
                    schema_id=schema.schema_id,
                    part=part,
                    area_coords=area_coords,
                    declared_sizes=declared_sizes,
                )
                if row is None:
                    continue
                seen_keys.add(dedup_key)
                rows.append(row)
                added += 1
            if added >= PARTS_PER_GROUP:
                break
        return added

    for vehicle_model, market in TARGET_MODELS:
        specs = pick_specs(conn, vehicle_model, market)
        for spec in specs:
            categories = pick_categories(conn, spec["stable_key"])
            for category_slug in categories:
                group = pick_group(conn, spec["stable_key"], category_slug)
                if group is None:
                    continue
                add_group(vehicle_model, spec, category_slug, group["group_id"])

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=HUBBI_COLUMNS, quoting=csv.QUOTE_MINIMAL)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    print(f"wrote {len(rows)} rows to {OUT_PATH}")

    # Confere de fato quantos modelos distintos entraram e se o exemplo
    # multi-aplicação realmente apareceu.
    by_model: dict[str, int] = defaultdict(int)
    oem_counter: dict[str, set[str]] = defaultdict(set)
    for r in rows:
        model = r["application"].split(" - ")[0].split("VOLKSWAGEN ", 1)[-1]
        by_model[model] += 1
        oem_counter[r["manufacturer_ref"]].add(r["application"])
    print("rows per model:", dict(by_model))
    multi_app = {oem: sorted(apps) for oem, apps in oem_counter.items() if len(apps) > 1}
    print(
        "OEMs appearing in >1 application:",
        json.dumps(multi_app, indent=2, ensure_ascii=False)[:1500],
    )


if __name__ == "__main__":
    main()
