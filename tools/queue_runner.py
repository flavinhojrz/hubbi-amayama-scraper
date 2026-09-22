"""tools/queue_runner.py — orquestra a coleta de vários modelos/mercados em
paralelo, um processo scraper (`--workers 1`) por slot de Chrome/porta CDP,
puxando da fila (`vw_br_markets.txt`) o próximo alvo assim que um slot libera.

O que a automação FAZ:
  - Abre (uma vez, se ainda não estiver de pé) um Chrome dedicado por slot,
    com `--remote-debugging-port` fixo e `--user-data-dir` persistente — o
    mesmo Chrome/perfil é reaproveitado pra vários modelos ao longo da fila
    (sessão fica "aquecida", sem repetir o Turnstile de sessão nova a cada
    modelo).
  - Descobre o que já está completo direto do banco
    (`collection_run.completed_at IS NOT NULL` pro scope) — sem arquivo de
    estado próprio; reiniciar a automação recalcula a fila sozinho.
  - Mantém N slots ocupados, lançando o próximo alvo pendente assim que um
    processo termina, sempre espaçando o lançamento de sessões (mesma causa
    raiz do Turnstile em rajada que já vimos ao vivo).

O que a automação NÃO faz:
  - Nunca resolve captcha sozinha. Cada processo filho já espera
    indefinidamente (sem `--challenge-timeout`) quando cai em challenge — o
    operador resolve manualmente (ou via bot próprio) na janela do Chrome
    correspondente quando aparecer. `tools/monitor.py --watch`, em outro
    terminal, mostra o progresso agregado.

Uso:
    python tools/queue_runner.py
    python tools/queue_runner.py --slots 4 --base-port 9222
    python tools/queue_runner.py --list vw_br_markets.txt --db-path amayama.db
"""

from __future__ import annotations

import argparse
import re
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LIST_PATH = PROJECT_ROOT / "vw_br_markets.txt"
DEFAULT_CHROME_PATH = Path("C:/Program Files/Google/Chrome/Application/chrome.exe")
DEFAULT_PYTHON_EXE = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
_MIN_LAUNCH_GAP_SECONDS = 15.0  # espaçamento mínimo entre lançar sessões novas
_SLUG_RE = re.compile(r"/volkswagen-overall/([^/]+)/")


@dataclass
class Target:
    vehicle_model: str
    market: str
    display_name: str

    @property
    def key(self) -> tuple[str, str]:
        return (self.vehicle_model, self.market)


@dataclass
class Slot:
    index: int
    port: int
    profile_dir: Path
    process: subprocess.Popen | None = None
    target: Target | None = None
    started_at: float = 0.0


def parse_targets(list_path: Path) -> list[Target]:
    """Deriva vehicle_model do SLUG da URL (não do nome de exibição) — o
    slug já é seguro pra --vehicle-model (só letras/dígitos/hífen), o nome
    de exibição pode ter espaços/parênteses/barras que a CLI rejeitaria."""
    targets: list[Target] = []
    seen: set[tuple[str, str]] = set()
    for line in list_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) != 3:
            continue
        display_name, market, url = parts
        slug_match = _SLUG_RE.search(url)
        if not slug_match:
            continue
        vehicle_model = slug_match.group(1).upper()
        market_norm = market.upper()
        key = (vehicle_model, market_norm)
        if key in seen:
            continue
        seen.add(key)
        targets.append(
            Target(vehicle_model=vehicle_model, market=market_norm, display_name=display_name)
        )
    return targets


def load_done_scopes(db_path: str) -> set[tuple[str, str]]:
    """(vehicle_model, market) já com CollectionRun.completed_at setado —
    mesma leitura WAL-aware de tools/monitor.py, feita uma única vez no
    início (a fila já fica fixa depois de calculada; os alvos que a própria
    automação vai rodar não precisam ser reconsultados)."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from monitor import _connect_ro  # reusa a mesma leitura segura de WAL

    conn = _connect_ro(db_path)
    try:
        rows = conn.execute(
            "SELECT scope FROM collection_run WHERE completed_at IS NOT NULL"
        ).fetchall()
    except sqlite3.OperationalError:
        return set()
    finally:
        conn.close()
    done: set[tuple[str, str]] = set()
    for row in rows:
        parts = row[0].split(":")
        if len(parts) >= 2:
            done.add((parts[-2], parts[-1]))
    return done


def _chrome_reachable(port: int) -> bool:
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=2)  # noqa: S310
        return True
    except (urllib.error.URLError, OSError):
        return False


def ensure_chrome(port: int, profile_dir: Path, chrome_path: Path) -> None:
    if _chrome_reachable(port):
        return
    profile_dir.mkdir(parents=True, exist_ok=True)
    subprocess.Popen(  # noqa: S603 - caminho/args fixos, nunca de input externo
        [str(chrome_path), f"--remote-debugging-port={port}", f"--user-data-dir={profile_dir}"],
        creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
    )
    for _ in range(30):
        if _chrome_reachable(port):
            return
        time.sleep(1)
    raise RuntimeError(f"Chrome na porta {port} não respondeu a tempo")


def launch_target(
    slot: Slot, target: Target, db_path: str, python_exe: str, poll_interval: float
) -> subprocess.Popen:
    cmd = [
        python_exe,
        "-m",
        "amayama_scraper.cli.main",
        "run",
        "--new-run",
        "--manufacturer",
        "VOLKSWAGEN",
        "--vehicle-model",
        target.vehicle_model,
        "--market",
        target.market,
        "--workers",
        "1",
        "--cdp-port",
        str(slot.port),
        "--db-path",
        db_path,
        "--challenge-poll-interval",
        str(poll_interval),
    ]
    return subprocess.Popen(cmd, cwd=PROJECT_ROOT)  # noqa: S603


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--list", default=str(DEFAULT_LIST_PATH))
    parser.add_argument("--db-path", default="amayama.db")
    parser.add_argument("--slots", type=int, default=4)
    parser.add_argument("--base-port", type=int, default=9222)
    parser.add_argument("--chrome-path", default=str(DEFAULT_CHROME_PATH))
    parser.add_argument("--python-exe", default=str(DEFAULT_PYTHON_EXE))
    parser.add_argument("--poll-interval", type=float, default=1.0)
    parser.add_argument("--check-interval", type=float, default=5.0)
    args = parser.parse_args()

    all_targets = parse_targets(Path(args.list))
    done = load_done_scopes(args.db_path)
    queue = [t for t in all_targets if t.key not in done]

    print(f"{len(all_targets)} alvos na lista, {len(done)} já completos, {len(queue)} na fila.")
    if not queue:
        print("Nada pendente.")
        return 0

    slots = [
        Slot(
            index=i,
            port=args.base_port + i,
            profile_dir=Path.home() / "AppData" / "Local" / "Temp" / f"amayama-queue-slot-{i}",
        )
        for i in range(args.slots)
    ]

    chrome_path = Path(args.chrome_path)
    for slot in slots:
        print(f"[slot {slot.index}] garantindo Chrome na porta {slot.port}...")
        ensure_chrome(slot.port, slot.profile_dir, chrome_path)

    last_launch_at = 0.0

    def try_launch(slot: Slot) -> None:
        nonlocal last_launch_at
        if not queue:
            return
        wait = _MIN_LAUNCH_GAP_SECONDS - (time.monotonic() - last_launch_at)
        if wait > 0:
            time.sleep(wait)
        target = queue.pop(0)
        print(
            f"[slot {slot.index}] iniciando {target.display_name} "
            f"({target.vehicle_model} {target.market}) na porta {slot.port}"
        )
        slot.process = launch_target(
            slot, target, args.db_path, args.python_exe, args.poll_interval
        )
        slot.target = target
        slot.started_at = time.monotonic()
        last_launch_at = time.monotonic()

    for slot in slots:
        try_launch(slot)

    try:
        while True:
            time.sleep(args.check_interval)
            any_active = False
            for slot in slots:
                if slot.process is None:
                    if queue:
                        try_launch(slot)
                        any_active = True
                    continue
                ret = slot.process.poll()
                if ret is None:
                    any_active = True
                    continue
                elapsed_min = (time.monotonic() - slot.started_at) / 60.0
                status = "OK" if ret == 0 else f"exitcode={ret}"
                assert slot.target is not None
                print(
                    f"[slot {slot.index}] {slot.target.display_name} terminou "
                    f"({status}, {elapsed_min:.1f}min)"
                )
                slot.process = None
                slot.target = None
                if queue:
                    try_launch(slot)
                    any_active = True
            if not any_active and not queue:
                print("Fila vazia, nenhum slot ativo. Fim.")
                return 0
            running = sum(1 for s in slots if s.process is not None)
            print(f"--- {len(queue)} na fila, {running} rodando ---")
    except KeyboardInterrupt:
        print("\nInterrompido — encerrando processos filhos (Chrome continua aberto)...")
        for slot in slots:
            if slot.process is not None and slot.process.poll() is None:
                slot.process.terminate()
        for slot in slots:
            if slot.process is not None:
                try:
                    slot.process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    slot.process.kill()
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
