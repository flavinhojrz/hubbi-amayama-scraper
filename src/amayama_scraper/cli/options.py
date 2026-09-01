"""Definição argparse — contracts/orchestration-contract.md §4.

Entrypoint fino: apenas define/parseia opções. Nenhuma lógica de domínio,
nenhuma composição de adapters (isso é cli/main.py). --resume/--new-run
são mutuamente exclusivos por construção do parser — a CLI recusa a
combinação antes de qualquer chamada a run_selection.select_run().
"""

from __future__ import annotations

import argparse

from amayama_scraper.transport.port import DEFAULT_BACKOFF_SECONDS, DEFAULT_MAX_RETRIES


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="amayama-scraper",
        description="Scraper real Amarok AMA-BR — navegador assistido, human-in-the-loop e resume.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser(
        "run", help="Executa (ou planeja, com --dry-run) uma coleta."
    )

    run_selection_group = run_parser.add_mutually_exclusive_group()
    run_selection_group.add_argument(
        "--resume",
        metavar="RUN_ID",
        default=None,
        help="Continua explicitamente um run existente (DEC-005).",
    )
    run_selection_group.add_argument(
        "--new-run",
        action="store_true",
        help="Força uma nova execução mesmo havendo um run incompleto compatível (DEC-005).",
    )

    run_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Somente leitura: exibe o plano operacional, nunca navega/escreve (DEC-009).",
    )
    run_parser.add_argument("--limit-specs", type=int, default=None, metavar="N")
    run_parser.add_argument("--limit-groups", type=int, default=None, metavar="N")
    run_parser.add_argument(
        "--spec",
        action="append",
        default=None,
        metavar="STABLE_KEY",
        help="Restringe a specs já descobertas (repetível, FR-025).",
    )
    run_parser.add_argument(
        "--retry-rejected",
        action="store_true",
        help="Inclui unidades REQUIRES_EXPLICIT_RETRY nesta passada (DEC-006).",
    )
    run_parser.add_argument(
        "--force",
        action="append",
        default=None,
        metavar="STABLE_KEY",
        help="Bypassa o skip de já-VALID para essas specs (repetível, DEC-008).",
    )

    run_parser.add_argument(
        "--cdp-host", default=None, help="Default: 127.0.0.1 ou AMAYAMA_CDP_HOST."
    )
    run_parser.add_argument(
        "--cdp-port", type=int, default=None, help="Default: 9222 ou AMAYAMA_CDP_PORT."
    )

    run_parser.add_argument("--min-interval", type=float, default=0.0, metavar="SECONDS")
    run_parser.add_argument(
        "--transport-max-retries", type=int, default=DEFAULT_MAX_RETRIES, metavar="N"
    )
    run_parser.add_argument(
        "--transport-backoff-seconds",
        type=float,
        default=DEFAULT_BACKOFF_SECONDS,
        metavar="SECONDS",
    )
    run_parser.add_argument("--challenge-poll-interval", type=float, default=5.0, metavar="SECONDS")
    run_parser.add_argument(
        "--challenge-timeout",
        type=float,
        default=None,
        metavar="SECONDS",
        help="Ausente = espera indefinida (research.md §11).",
    )

    run_parser.add_argument("--db-path", default=None, metavar="PATH")
    run_parser.add_argument("--raw-root", default=None, metavar="PATH")

    return parser


def parse_args(argv: list[str]) -> argparse.Namespace:
    return build_arg_parser().parse_args(argv)
