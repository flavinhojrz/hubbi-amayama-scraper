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
        description=(
            "Scraper real Amayama — navegador assistido, human-in-the-loop e resume. "
            "Reutilizável para qualquer modelo/mercado Volkswagen via "
            "--manufacturer/--vehicle-model/--market (default: VOLKSWAGEN/AMAROK/AMA-BR)."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser(
        "run", help="Executa (ou planeja, com --dry-run) uma coleta."
    )

    run_parser.add_argument(
        "--manufacturer",
        default="VOLKSWAGEN",
        metavar="MANUFACTURER",
        help="Fabricante a coletar (default: VOLKSWAGEN).",
    )
    run_parser.add_argument(
        "--vehicle-model",
        default="AMAROK",
        metavar="VEHICLE_MODEL",
        help="Modelo do veículo a coletar (default: AMAROK).",
    )
    run_parser.add_argument(
        "--market",
        default="AMA-BR",
        metavar="MARKET",
        help="Mercado Amayama a coletar (default: AMA-BR).",
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

    run_parser.add_argument(
        "--workers",
        type=int,
        default=1,
        metavar="N",
        help=(
            "Paralelismo controlado por spec, 1-4 (default: 1 — comportamento legado "
            "bit-a-bit, 005 FR-001/FR-003)."
        ),
    )
    run_parser.add_argument(
        "--cdp-ports",
        default=None,
        metavar="PORT,PORT,...",
        help=(
            "Uma porta CDP por worker (--workers N), separadas por vírgula — um Chrome real "
            "distinto por porta (005 FR-042). Default: deriva de --cdp-port/AMAYAMA_CDP_PORT/9222 "
            "como porta-base, uma porta consecutiva por índice de worker."
        ),
    )
    run_parser.add_argument(
        "--lease-seconds",
        type=float,
        default=120.0,
        metavar="SECONDS",
        help=(
            "Duração do lease de claim por spec antes de se tornar recuperável (005 FR-021/FR-023)."
        ),
    )
    run_parser.add_argument(
        "--challenge-window-seconds",
        type=float,
        default=300.0,
        metavar="SECONDS",
        help="Janela de observação de challenges para o rate limiter adaptativo (005 FR-063).",
    )
    run_parser.add_argument(
        "--challenge-threshold",
        type=int,
        default=1,
        metavar="N",
        help="Número de challenges na janela que aciona uma redução de concorrência (005 FR-063).",
    )
    run_parser.add_argument(
        "--stability-seconds",
        type=float,
        default=600.0,
        metavar="SECONDS",
        help="Período sem challenge exigido para recuperar 1 nível de concorrência (005 FR-064).",
    )
    run_parser.add_argument(
        "--metrics-interval-seconds",
        type=float,
        default=30.0,
        metavar="SECONDS",
        help="Intervalo entre relatórios de métricas do orquestrador (005 FR-070).",
    )

    return parser


def parse_args(argv: list[str]) -> argparse.Namespace:
    return build_arg_parser().parse_args(argv)
