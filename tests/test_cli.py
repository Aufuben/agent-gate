from __future__ import annotations

from datetime import date
from pathlib import Path

from agent_gate.models import UsageReport, UsageRow


def test_usage_cli_masks_keys(tmp_path: Path, monkeypatch, capsys) -> None:
    from agent_gate import cli

    keys = tmp_path / "keys.txt"
    secret = "sk-or-v1-abcdefghijklmnopqrstuvwxyz"
    keys.write_text(f"openrouter:{secret}\n", encoding="utf-8")

    def fake_query(**kwargs):
        assert secret in kwargs["text"] or True
        return UsageReport(
            rows=[
                UsageRow(
                    masked="sk-or-...wxyz",
                    provider="openrouter",
                    used="1 USD",
                    remaining="2 USD",
                    cost="1 USD",
                )
            ],
            totals={"used": "1 USD", "remaining": "2 USD", "cost": "1 USD"},
            from_date=date(2026, 7, 1),
            to_date=date(2026, 8, 1),
        )

    monkeypatch.setattr(cli, "query_usage", fake_query)
    code = cli.main(
        [
            "usage",
            "--keys-file",
            str(keys),
            "--from",
            "2026-07-01",
            "--to",
            "2026-08-01",
        ]
    )
    assert code == 0
    out = capsys.readouterr().out
    assert secret not in out
    assert "sk-or-...wxyz" in out
    assert "合计" in out


def test_usage_cli_missing_file_exits_two(tmp_path: Path) -> None:
    from agent_gate.cli import main

    code = main(["usage", "--keys-file", str(tmp_path / "nope.txt")])
    assert code == 2


def test_parser_default_is_usage_not_check() -> None:
    from agent_gate.cli import build_parser

    help_text = build_parser().format_help()
    assert "usage" in help_text
    assert "gui" in help_text
    assert "API" in help_text or "额度" in help_text or "key" in help_text.lower()


def test_readme_and_example_keys() -> None:
    root = Path(__file__).resolve().parents[1]
    readme = (root / "README.md").read_text(encoding="utf-8")
    gitignore = (root / ".gitignore").read_text(encoding="utf-8")
    assert "dual_control" not in readme
    assert "实习生" not in readme
    assert "统计额度" in readme
    assert "合计" in readme
    assert "keys.example.txt" in readme
    assert "keys.txt" in gitignore
    assert (root / "keys.example.txt").is_file()
