from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_POLICY = ROOT / "policies" / "example.yaml"


def test_demo_exits_zero_on_expected_flow(tmp_path: Path) -> None:
    from agent_gate.legacy.demo import EXIT_OK, run_demo

    code = run_demo(
        policy_path=EXAMPLE_POLICY,
        audit_path=tmp_path / "audit.jsonl",
    )
    assert code == EXIT_OK
