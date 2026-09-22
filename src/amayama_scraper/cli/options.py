"""Definição argparse — contracts/orchestration-contract.md §4.

Entrypoint fino: apenas define/parseia opções. Nenhuma lógica de domínio,
nenhuma composição de adapters (isso é cli/main.py). --resume/--new-run
são mutuamente exclusivos por construção do parser — a CLI recusa a
combinação antes de qualquer chamada a run_selection.select_run().
"""

from __future__ import annotations

import argparse

from amayama_scraper.transport.port import (
    DEFAULT_BACKOFF_SECONDS,
    DEFAULT_DETAIL_FETCH_BATCH_SIZE,
    DEFAULT_DETAIL_FETCH_CHUNK_SIZE,
    DEFAULT_DETAIL_FETCH_TIMEOUT_MS,
    DEFAULT_MAX_RETRIES,
)


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
        "--repair-manifest",
        action="store_true",
        help=(
            "Repair/backfill: redescobre o manifesto categoria-a-categoria para specs já "
            "existentes no escopo (--manufacturer/--vehicle-model/--market), mesmo com um "
            "manifesto anterior já marcado manifest_complete=1 — nunca apaga checkpoints "
            "ACCEPTED, só grupos ainda ausentes viram trabalho pendente. Reabre o "
            "CollectionRun mais recente do escopo (limpa completed_at) em vez de criar um "
            "run novo, preservando o progresso já aceito. --resume/--new-run são ignorados "
            "com este flag (incompatível com a seleção de run normal)."
        ),
    )
    run_parser.add_argument(
        "--repair-all-scopes",
        action="store_true",
        help=(
            "Só com --repair-manifest: repara TODO escopo (vehicle_model/market) já "
            "coletado sob --manufacturer, em vez de apenas --vehicle-model/--market — "
            "deriva a lista diretamente dos CollectionRun já existentes no banco (nenhum "
            "arquivo/lista externa necessária). Repara Volkswagen BR inteiro: "
            "--manufacturer VOLKSWAGEN --repair-manifest --repair-all-scopes (mercados são "
            "parte de cada scope já persistido, não precisam ser listados)."
        ),
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
        "--own-chrome",
        action="store_true",
        help=(
            "Usa transport/undetected_chrome_adapter.py: cada worker lança seu PRÓPRIO "
            "Chrome (perfil herdado do operador) em vez de anexar a um Chrome já aberto "
            "(--cdp-host/--cdp-port, comportamento default) — e "
            "resolve reCAPTCHA automaticamente via CAPTCHA_API_URL/TOKEN_API quando "
            "configurados (sem isso, challenge ainda aguarda o operador na janela visível)."
        ),
    )
    run_parser.add_argument(
        "--chrome-headless",
        action="store_true",
        help="Só com --own-chrome: roda o Chrome próprio sem janela visível.",
    )

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

    run_parser.add_argument(
        "--no-detail-batch-fetch",
        action="store_true",
        help=(
            "Desliga o fetch em lote de GROUP_DETAIL (validado em spikes/batched_fetch_spike.py: "
            "~5.900 requisições reais contra o Amayama, 0 challenges em modo lote vs. ~90-100%% "
            "em modo navigate único) — volta ao navigate() único por grupo. Ligado por padrão."
        ),
    )
    run_parser.add_argument(
        "--detail-fetch-batch-size",
        type=int,
        default=DEFAULT_DETAIL_FETCH_BATCH_SIZE,
        metavar="N",
        help="Grupos pendentes buscados por chamada de fetch em lote.",
    )
    run_parser.add_argument(
        "--detail-fetch-chunk-size",
        type=int,
        default=DEFAULT_DETAIL_FETCH_CHUNK_SIZE,
        metavar="N",
        help="Concorrência (fetch() simultâneos) dentro de cada chamada de fetch em lote.",
    )
    run_parser.add_argument(
        "--detail-fetch-timeout-ms",
        type=int,
        default=DEFAULT_DETAIL_FETCH_TIMEOUT_MS,
        metavar="MS",
        help="Timeout por URL individual dentro do fetch em lote.",
    )

    return parser


def parse_args(argv: list[str]) -> argparse.Namespace:
    return build_arg_parser().parse_args(argv)
