"""T023 — cli/analyze.py::build_arg_parser(): 4 subcomandos, flags obrigatórios, --json opcional."""

import pytest

from amayama_scraper.cli.analyze import parse_args


def test_summary_requires_scope_flags():
    with pytest.raises(SystemExit):
        parse_args(["summary"])


def test_summary_parses_scope_and_defaults_json_to_false():
    args = parse_args(
        [
            "summary",
            "--manufacturer",
            "VOLKSWAGEN",
            "--vehicle-model",
            "AMAROK",
            "--market",
            "AMA-BR",
        ]
    )
    assert args.command == "summary"
    assert args.manufacturer == "VOLKSWAGEN"
    assert args.json is False


def test_quality_and_redundancy_accept_json_flag():
    for command in ("quality", "redundancy"):
        args = parse_args(
            [
                command,
                "--manufacturer",
                "VOLKSWAGEN",
                "--vehicle-model",
                "AMAROK",
                "--market",
                "AMA-BR",
                "--json",
            ]
        )
        assert args.command == command
        assert args.json is True


def test_compare_requires_spec_a_and_spec_b_not_scope_flags():
    args = parse_args(["compare", "--spec-a", "key-a", "--spec-b", "key-b"])
    assert args.command == "compare"
    assert args.spec_a == "key-a"
    assert args.spec_b == "key-b"


def test_compare_without_both_specs_fails():
    with pytest.raises(SystemExit):
        parse_args(["compare", "--spec-a", "key-a"])


def test_unknown_command_fails():
    with pytest.raises(SystemExit):
        parse_args(["nonexistent"])
