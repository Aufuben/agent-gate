from __future__ import annotations

from pathlib import Path

from tests.conftest import EXAMPLE_POLICY


def test_cli_check_intern_prod_restart_exits_one() -> None:
    from agent_gate.cli import main

    code = main(
        [
            "check",
            "--policy",
            str(EXAMPLE_POLICY),
            "--role",
            "intern",
            "--tool",
            "prod_restart",
        ]
    )
    assert code == 1


def test_cli_check_intern_read_file_exits_zero() -> None:
    from agent_gate.cli import main

    code = main(
        [
            "check",
            "--policy",
            str(EXAMPLE_POLICY),
            "--role",
            "intern",
            "--tool",
            "read_file",
        ]
    )
    assert code == 0


def test_cli_record_approve_export(tmp_path: Path) -> None:
    from agent_gate.cli import main

    audit = tmp_path / "audit.jsonl"
    csv_path = tmp_path / "audit.csv"
    assert (
        main(
            [
                "record",
                "--audit",
                str(audit),
                "--session",
                "S",
                "--actor",
                "a",
                "--tool",
                "read_file",
                "--args",
                "{}",
                "--decision",
                "allow",
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "approve",
                "--audit",
                str(audit),
                "--session",
                "S",
                "--tool",
                "prod_restart",
                "--approver",
                "alice",
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "export-audit",
                "--audit",
                str(audit),
                "--from",
                "2020-01-01",
                "--out",
                str(csv_path),
            ]
        )
        == 0
    )
    assert csv_path.stat().st_size > 0
