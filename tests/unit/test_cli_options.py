"""T095 — parsing de argumentos (contracts/orchestration-contract.md §4).
Todas as flags aceitas com os tipos corretos; --resume/--new-run mutuamente
exclusivos (erro de uso antes de qualquer lógica de orquestração); --spec/
--force são repetíveis."""

from __future__ import annotations

import pytest

from amayama_scraper.cli.options import parse_args


def test_run_with_no_flags_uses_defaults() -> None:
    args = parse_args(["run"])
    assert args.command == "run"
    assert args.resume is None
    assert args.new_run is False
    assert args.dry_run is False
    assert args.limit_specs is None
    assert args.limit_groups is None
    assert args.spec is None
    assert args.retry_rejected is False
    assert args.force is None
    # Defaults preservam compatibilidade com o comportamento histórico
    # (Amarok/AMA-BR) da feature 002 antes da evolução multi-modelo.
    assert args.manufacturer == "VOLKSWAGEN"
    assert args.vehicle_model == "AMAROK"
    assert args.market == "AMA-BR"


def test_manufacturer_vehicle_model_and_market_are_overridable() -> None:
    args = parse_args(
        ["run", "--manufacturer", "VOLKSWAGEN", "--vehicle-model", "GOL", "--market", "AMA-BR"]
    )
    assert args.manufacturer == "VOLKSWAGEN"
    assert args.vehicle_model == "GOL"
    assert args.market == "AMA-BR"


def test_resume_accepts_run_id() -> None:
    args = parse_args(["run", "--resume", "abc-123"])
    assert args.resume == "abc-123"


def test_new_run_flag() -> None:
    args = parse_args(["run", "--new-run"])
    assert args.new_run is True


def test_resume_and_new_run_are_mutually_exclusive() -> None:
    with pytest.raises(SystemExit):
        parse_args(["run", "--resume", "abc-123", "--new-run"])


def test_dry_run_flag() -> None:
    args = parse_args(["run", "--dry-run"])
    assert args.dry_run is True


def test_limit_specs_and_limit_groups_are_ints() -> None:
    args = parse_args(["run", "--limit-specs", "2", "--limit-groups", "5"])
    assert args.limit_specs == 2
    assert args.limit_groups == 5


def test_spec_is_repeatable() -> None:
    args = parse_args(["run", "--spec", "key-a", "--spec", "key-b"])
    assert args.spec == ["key-a", "key-b"]


def test_force_is_repeatable() -> None:
    args = parse_args(["run", "--force", "key-a", "--force", "key-b"])
    assert args.force == ["key-a", "key-b"]


def test_retry_rejected_flag() -> None:
    args = parse_args(["run", "--retry-rejected"])
    assert args.retry_rejected is True


def test_cdp_host_and_port() -> None:
    args = parse_args(["run", "--cdp-host", "10.0.0.5", "--cdp-port", "9333"])
    assert args.cdp_host == "10.0.0.5"
    assert args.cdp_port == 9333


def test_transport_and_challenge_tuning_flags() -> None:
    args = parse_args(
        [
            "run",
            "--min-interval",
            "1.5",
            "--transport-max-retries",
            "5",
            "--transport-backoff-seconds",
            "3.0",
            "--challenge-poll-interval",
            "10.0",
            "--challenge-timeout",
            "600",
        ]
    )
    assert args.min_interval == 1.5
    assert args.transport_max_retries == 5
    assert args.transport_backoff_seconds == 3.0
    assert args.challenge_poll_interval == 10.0
    assert args.challenge_timeout == 600.0


def test_db_path_and_raw_root() -> None:
    args = parse_args(["run", "--db-path", "/tmp/x.db", "--raw-root", "/tmp/raw"])
    assert args.db_path == "/tmp/x.db"
    assert args.raw_root == "/tmp/raw"
