from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_POLICY = ROOT / "policies" / "example.yaml"


def test_demo_exit_codes_documented() -> None:
    from agent_gate.demo import EXIT_OK, EXIT_UNEXPECTED, EXIT_USAGE

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "退出码" in readme
    for code, label in (
        (EXIT_OK, "0"),
        (EXIT_UNEXPECTED, "1"),
        (EXIT_USAGE, "2"),
    ):
        assert str(code) == label
        assert label in readme


def test_demo_exits_zero_on_expected_flow(tmp_path: Path) -> None:
    from agent_gate.demo import EXIT_OK, run_demo

    code = run_demo(
        policy_path=EXAMPLE_POLICY,
        audit_path=tmp_path / "audit.jsonl",
    )
    assert code == EXIT_OK
