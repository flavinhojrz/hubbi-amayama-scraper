"""Detector de CHALLENGE — CAPTCHA/Cloudflare/"Just a moment" (Constitution §5, FR-010).

Heurísticas genéricas de challenge (não específicas da Amayama — padrões
de mercado bem documentados para Cloudflare/CAPTCHA). Nunca tenta resolver
o challenge — apenas detectar sua presença para roteamento human-in-the-loop.

Issue #8 (correção original): `g-recaptcha` deixou de ser um marker de
substring pura — o template global real da Amayama embute um widget
reCAPTCHA benigno dentro dos modais de cadastro/recuperação de senha
(`#registration-form-container`, `#restore-form-container`) em toda página
EPC real, o que produzia falso positivo de CHALLENGE em páginas sem
challenge algum.

Issue #8 (blocker material, correção desta revisão): a primeira correção
determinava o pertencimento de `.g-recaptcha` a esses containers
exclusivamente via DOM parseado (BeautifulSoup/lxml). Nas próprias
fixtures reais completas, esse markup está embutido dentro de um
`<script type="text/x-handlebars-template">` — que nenhum parser HTML
conforme a spec materializa como DOM (conteúdo de `<script>` é sempre
texto opaco, qualquer que seja o `type`). Resultado: o HTML bruto contém
2 ocorrências reais de `g-recaptcha`, mas `soup.select(".g-recaptcha")`
encontra 0 elementos — logo, se os ids aprovados forem renomeados dentro
desse mesmo bloco, a checagem por DOM não encontra nada em nenhum dos dois
lados e silenciosamente devolve `detected=False`. Corrigido: o
pertencimento a um container benigno agora é decidido primariamente sobre
o HTML BRUTO (varredura de texto, balanceamento de profundidade de
`<div>`/`</div>` a partir do `id="..."` aprovado — nunca dependente do
parser materializar nada), com o DOM mantido apenas como sinal adicional
que só pode ADICIONAR detecção, nunca subtraí-la. Fail closed: uma
ocorrência de `g-recaptcha` só é ignorada quando é possível comprovar,
deterministicamente, que seu offset cai dentro do span balanceado de um
`id` exatamente aprovado; qualquer ocorrência não comprovada — porque o id
foi renomeado, removido, ou está fora de qualquer container — conta como
sinal de challenge.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from amayama_scraper.validation.detectors.base import DetectionResult

_TITLE_MARKERS = ("just a moment", "attention required", "checking your browser")
_ID_OR_CLASS_MARKERS = (
    "cf-challenge-running",
    "cf-wrapper",
    "cf-browser-verification",
    "challenge-running",
    "challenge-form",
    "h-captcha",
)
_TEXT_MARKERS = (
    "verify you are human",
    "checking if the site connection is secure",
    "enable javascript and cookies to continue",
    "ray id:",
)

#: Known benign containers (site-wide sign-up/restore-password modals) whose
#: reCAPTCHA widget is never an EPC page challenge (Issue #8).
_BENIGN_RECAPTCHA_CONTAINER_IDS = ("registration-form-container", "restore-form-container")

_RECAPTCHA_TOKEN = "g-recaptcha"
_RECAPTCHA_TOKEN_RE = re.compile(re.escape(_RECAPTCHA_TOKEN))
_BENIGN_CONTAINER_ID_ATTR_RE = re.compile(
    r'id\s*=\s*(["\'])\s*(?:'
    + "|".join(re.escape(cid) for cid in _BENIGN_RECAPTCHA_CONTAINER_IDS)
    + r")\s*\1"
)
_DIV_OPEN_RE = re.compile(r"<div\b")
_DIV_CLOSE_RE = re.compile(r"</div\s*>")


def _raw_div_span(lowered_html: str, tag_start: int) -> tuple[int, int]:
    """Balances `<div>`/`</div>` by linear depth counting over the raw HTML
    TEXT (never a parsed DOM), starting at the `<div` opening tag found at
    `tag_start`. This is what lets a benign-container's real boundary be
    established even when a surrounding `<script>` wrapper (e.g. a
    Handlebars template) makes the same content unparseable as DOM — `<div`/
    `</div>` tokens are not affected by that corruption. If the document
    ends before depth returns to 0 (malformed HTML), the span conservatively
    extends to end of document rather than raising."""
    open_tag_end = lowered_html.find(">", tag_start)
    if open_tag_end == -1:
        return tag_start, len(lowered_html)

    pos = open_tag_end + 1
    depth = 1
    while depth > 0:
        next_open = _DIV_OPEN_RE.search(lowered_html, pos)
        next_close = _DIV_CLOSE_RE.search(lowered_html, pos)
        if next_close is None:
            return tag_start, len(lowered_html)
        if next_open is not None and next_open.start() < next_close.start():
            depth += 1
            pos = next_open.end()
        else:
            depth -= 1
            pos = next_close.end()
    return tag_start, pos


def _benign_recaptcha_spans_raw(lowered_html: str) -> list[tuple[str, int, int]]:
    """Raw-text spans (container_id, start, end) of the known-benign
    containers actually present in this document, determined without any
    dependency on DOM parsing succeeding. An approved id string absent from
    the raw HTML produces no span at all — fail closed, never inferred from
    partial/fuzzy textual proximity."""
    spans: list[tuple[str, int, int]] = []
    for match in _BENIGN_CONTAINER_ID_ATTR_RE.finditer(lowered_html):
        tag_start = lowered_html.rfind("<div", 0, match.start())
        if tag_start == -1:
            continue
        container_id = next(cid for cid in _BENIGN_RECAPTCHA_CONTAINER_IDS if cid in match.group(0))
        start, end = _raw_div_span(lowered_html, tag_start)
        spans.append((container_id, start, end))
    return spans


def _detect_recaptcha_raw(lowered_html: str) -> tuple[bool, list[str]]:
    """True (challenge signal) if any raw `g-recaptcha` occurrence in the
    HTML text cannot be proven to fall inside a benign container's raw
    span. This is the authoritative, fail-closed check — it does not
    depend on the DOM materializing the widget or its container at all.
    Also returns which benign container ids actually accounted for at
    least one occurrence, for observability."""
    benign_spans = _benign_recaptcha_spans_raw(lowered_html)
    accounted_container_ids: set[str] = set()
    challenge = False
    for match in _RECAPTCHA_TOKEN_RE.finditer(lowered_html):
        offset = match.start()
        covering = [cid for cid, start, end in benign_spans if start <= offset < end]
        if covering:
            accounted_container_ids.update(covering)
        else:
            challenge = True
    return challenge, sorted(accounted_container_ids)


def _detect_recaptcha_dom(soup: BeautifulSoup) -> bool:
    """Supplementary DOM-based signal — only ever ADDS detection, never
    removes it (Issue #8 blocker: the DOM alone is not a trustworthy source
    of truth for this marker, since it can fail to materialize the widget
    entirely). Used only when the DOM does find `.g-recaptcha` elements."""
    for element in soup.select(".g-recaptcha"):
        has_benign_ancestor = any(
            element.find_parent(id=container_id) is not None
            for container_id in _BENIGN_RECAPTCHA_CONTAINER_IDS
        )
        if not has_benign_ancestor:
            return True
    return False


def detect_challenge(html: str) -> DetectionResult:
    lowered = html.lower()
    evidence: dict[str, object] = {}

    soup = BeautifulSoup(html, "lxml")
    title_text = ""
    if soup.title is not None and soup.title.string:
        title_text = soup.title.string.strip().lower()
    title_hits = [marker for marker in _TITLE_MARKERS if marker in title_text]
    if title_hits:
        evidence["title_markers"] = title_hits

    id_class_hits = [marker for marker in _ID_OR_CLASS_MARKERS if marker in lowered]

    if _RECAPTCHA_TOKEN in lowered:
        raw_challenge, accounted_container_ids = _detect_recaptcha_raw(lowered)
        recaptcha_is_challenge = raw_challenge or _detect_recaptcha_dom(soup)
        if recaptcha_is_challenge:
            id_class_hits.append(_RECAPTCHA_TOKEN)
        elif accounted_container_ids:
            evidence["benign_recaptcha_containers_confirmed"] = accounted_container_ids

    if id_class_hits:
        evidence["id_or_class_markers"] = id_class_hits

    text_hits = [marker for marker in _TEXT_MARKERS if marker in lowered]
    if text_hits:
        evidence["text_markers"] = text_hits

    detected = bool(title_hits or id_class_hits or text_hits)
    return DetectionResult(detected=detected, evidence=evidence)
