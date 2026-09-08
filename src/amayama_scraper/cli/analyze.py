"""cli/analyze.py — entrypoint independente da ferramenta de análise do corpus.

003-corpus-analysis-tool. Deliberadamente não importa nem é importado por
cli/main.py / cli/options.py (pertencem a 002-amarok-ama-br-browser-scraper,
em implementação não commitada nesta mesma branch) — ver plan.md "Por que um
entrypoint CLI separado". Somente leitura: nunca escreve no banco, nunca cria
o arquivo se ele não existir (persistence.db.connect_read_only).

Uso: `python -m amayama_scraper.cli.analyze <summary|quality|redundancy|compare> ...`
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

from amayama_scraper.analysis.comparison import compare_specs
from amayama_scraper.analysis.json_view import (
    quality_report_to_dict,
    redundancy_report_to_dict,
    scope_summary_to_dict,
    spec_comparison_to_dict,
)
from amayama_scraper.analysis.quality import assess_quality
from amayama_scraper.analysis.redundancy import build_redundancy_report
from amayama_scraper.analysis.render import (
    render_comparison_text,
    render_quality_text,
    render_redundancy_text,
    render_summary_text,
)
from amayama_scraper.analysis.summary import build_scope_summary
from amayama_scraper.analysis.types import ScopeIdentifier
from amayama_scraper.domain.identity import SpecIdentity
from amayama_scraper.domain.manifest import SpecGroupManifest, is_manifest_authoritative
from amayama_scraper.persistence.db import connect_read_only
from amayama_scraper.persistence.repositories.checkpoint_repo import list_accepted
from amayama_scraper.persistence.repositories.manifest_repo import list_for_spec
from amayama_scraper.persistence.repositories.snapshot_repo import list_latest_snapshot_per_spec
from amayama_scraper.persistence.repositories.spec_registry_repo import (
    get_spec_identity,
    list_by_scope,
)
from amayama_scraper.snapshots.snapshot import SpecSnapshot

DEFAULT_DB_PATH = "amayama.db"

_ScopeData = tuple[
    list[SpecIdentity],
    dict[str, SpecSnapshot],
    dict[str, list[tuple[str, SpecGroupManifest]]],
    dict[str, dict[str, frozenset[tuple[str, str]]]],
]


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="amayama-analyze",
        description=(
            "Análise somente-leitura do corpus coletado (amayama.db) — "
            "resumo, qualidade, redundância, comparação."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_scope_args(p: argparse.ArgumentParser) -> None:
        p.add_argument("--manufacturer", required=True)
        p.add_argument("--vehicle-model", required=True)
        p.add_argument("--market", required=True)

    def add_common_args(p: argparse.ArgumentParser) -> None:
        p.add_argument("--db-path", default=None, metavar="PATH")
        p.add_argument("--json", action="store_true", help="Saída JSON em vez de texto.")

    summary_parser = subparsers.add_parser("summary", help="Resumo geral de um escopo.")
    add_scope_args(summary_parser)
    add_common_args(summary_parser)

    quality_parser = subparsers.add_parser("quality", help="Auditoria de qualidade de um escopo.")
    add_scope_args(quality_parser)
    add_common_args(quality_parser)

    redundancy_parser = subparsers.add_parser(
        "redundancy", help="Redundância entre specs via fingerprints já persistidos."
    )
    add_scope_args(redundancy_parser)
    add_common_args(redundancy_parser)

    compare_parser = subparsers.add_parser(
        "compare", help="Comparação detalhada entre duas specs (por stable_key)."
    )
    compare_parser.add_argument("--spec-a", required=True, metavar="STABLE_KEY")
    compare_parser.add_argument("--spec-b", required=True, metavar="STABLE_KEY")
    add_common_args(compare_parser)

    return parser


def parse_args(argv: list[str]) -> argparse.Namespace:
    return build_arg_parser().parse_args(argv)


def _current_manifest(manifests: list[tuple[str, SpecGroupManifest]]) -> SpecGroupManifest | None:
    for _run_id, manifest in manifests:
        if is_manifest_authoritative(manifest):
            return manifest
    return None


def _load_scope_data(conn: sqlite3.Connection, scope: ScopeIdentifier) -> _ScopeData:
    specs = list_by_scope(
        conn,
        manufacturer=scope.manufacturer,
        vehicle_model=scope.vehicle_model,
        market=scope.market,
    )
    spec_refs = [spec.stable_key() for spec in specs]
    latest_snapshot_by_spec = list_latest_snapshot_per_spec(conn, spec_refs)
    manifests_by_spec = {ref: list_for_spec(conn, ref) for ref in spec_refs}

    # Codex finding #2: grupos ACCEPTED só contam quando são do MESMO run_id
    # do manifest vigente — nunca uma união entre runs (um grupo aceito num
    # run antigo não prova que o run atual o cobriu).
    accepted_by_spec_and_run: dict[str, dict[str, frozenset[tuple[str, str]]]] = {}
    for ref in spec_refs:
        per_run: dict[str, frozenset[tuple[str, str]]] = {}
        for run_id, _manifest in manifests_by_spec[ref]:
            if run_id not in per_run:
                per_run[run_id] = frozenset(
                    (entry.category_slug, entry.group_id)
                    for entry in list_accepted(conn, run_id, ref)
                )
        accepted_by_spec_and_run[ref] = per_run

    return specs, latest_snapshot_by_spec, manifests_by_spec, accepted_by_spec_and_run


def _run_summary(conn: sqlite3.Connection, scope: ScopeIdentifier, as_json: bool) -> str:
    specs, latest_snapshot_by_spec, _, _ = _load_scope_data(conn, scope)
    summary = build_scope_summary(scope, specs, latest_snapshot_by_spec)
    if as_json:
        return json.dumps(scope_summary_to_dict(summary), indent=2, sort_keys=True)
    return render_summary_text(summary)


def _run_quality(conn: sqlite3.Connection, scope: ScopeIdentifier, as_json: bool) -> str:
    specs, latest_snapshot_by_spec, manifests_by_spec, accepted_by_spec_and_run = _load_scope_data(
        conn, scope
    )
    report = assess_quality(
        scope, specs, latest_snapshot_by_spec, manifests_by_spec, accepted_by_spec_and_run
    )
    if as_json:
        return json.dumps(quality_report_to_dict(report), indent=2, sort_keys=True)
    return render_quality_text(report)


def _run_redundancy(conn: sqlite3.Connection, scope: ScopeIdentifier, as_json: bool) -> str:
    specs, latest_snapshot_by_spec, _, _ = _load_scope_data(conn, scope)
    report = build_redundancy_report(scope, specs, latest_snapshot_by_spec)
    if as_json:
        return json.dumps(redundancy_report_to_dict(report), indent=2, sort_keys=True)
    return render_redundancy_text(report)


def _run_compare(conn: sqlite3.Connection, spec_a: str, spec_b: str, as_json: bool) -> str | None:
    identity_a = get_spec_identity(conn, spec_a)
    identity_b = get_spec_identity(conn, spec_b)
    if identity_a is None or identity_b is None:
        missing = [
            key for key, ident in ((spec_a, identity_a), (spec_b, identity_b)) if ident is None
        ]
        print(
            f"error: stable_key não encontrado em spec_registry: {', '.join(missing)}",
            file=sys.stderr,
        )
        return None

    scope = ScopeIdentifier(
        manufacturer=identity_a.manufacturer,
        vehicle_model=identity_a.vehicle_model,
        market=identity_a.market,
    )
    snapshots = list_latest_snapshot_per_spec(conn, [spec_a, spec_b])
    manifest_a = _current_manifest(list_for_spec(conn, spec_a))
    manifest_b = _current_manifest(list_for_spec(conn, spec_b))
    comparison = compare_specs(
        scope,
        identity_a,
        identity_b,
        snapshots.get(spec_a),
        snapshots.get(spec_b),
        manifest_a,
        manifest_b,
    )
    if as_json:
        return json.dumps(spec_comparison_to_dict(comparison), indent=2, sort_keys=True)
    return render_comparison_text(comparison)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    db_path = str(args.db_path or DEFAULT_DB_PATH)

    if not Path(db_path).exists():
        print(
            f"error: banco não encontrado em {db_path!r} — "
            "a ferramenta de análise nunca cria o banco.",
            file=sys.stderr,
        )
        return 2

    # Codex finding #4: um arquivo que existe mas não é um SQLite válido, ou
    # um SQLite válido sem o schema esperado, deve virar mensagem curta em
    # stderr (nunca traceback), exit code 2 — nunca propagar sqlite3.Error.
    try:
        conn = connect_read_only(db_path)
    except sqlite3.Error as exc:
        print(f"error: falha ao abrir o banco em {db_path!r}: {exc}", file=sys.stderr)
        return 2

    try:
        output: str | None
        if args.command == "compare":
            output = _run_compare(conn, args.spec_a, args.spec_b, args.json)
            if output is None:
                return 2
        else:
            scope = ScopeIdentifier(
                manufacturer=args.manufacturer,
                vehicle_model=args.vehicle_model,
                market=args.market,
            )
            if args.command == "summary":
                output = _run_summary(conn, scope, args.json)
            elif args.command == "quality":
                output = _run_quality(conn, scope, args.json)
            elif args.command == "redundancy":
                output = _run_redundancy(conn, scope, args.json)
            else:  # pragma: no cover - argparse já restringe choices
                raise ValueError(f"unknown command {args.command!r}")
    except sqlite3.Error as exc:
        print(f"error: falha ao ler o banco em {db_path!r}: {exc}", file=sys.stderr)
        return 2
    finally:
        conn.close()

    print(output)
    return 0


if __name__ == "__main__":  # pragma: no cover - thin process entrypoint
    raise SystemExit(main())
