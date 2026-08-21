from __future__ import annotations

from pathlib import Path


def test_intern_denied_prod_restart(gate) -> None:
    result = gate.check(role="intern", tool="prod_restart", actor="intern-1")
    assert result.allowed is False
    assert result.decision == "deny"


def test_sre_denied_prod_restart_until_two_distinct_approvers(gate) -> None:
    session = "S-dual"
    first = gate.check(
        role="sre", tool="prod_restart", actor="sre-1", session=session
    )
    assert first.allowed is False

    gate.approve(session=session, tool="prod_restart", approver="alice")
    after_one = gate.check(
        role="sre", tool="prod_restart", actor="sre-1", session=session
    )
    assert after_one.allowed is False

    gate.approve(session=session, tool="prod_restart", approver="bob")
    after_two = gate.check(
        role="sre", tool="prod_restart", actor="sre-1", session=session
    )
    assert after_two.allowed is True
    assert after_two.decision == "allow"


def test_same_approver_twice_does_not_count(gate) -> None:
    session = "S-same"
    gate.approve(session=session, tool="prod_restart", approver="alice")
    gate.approve(session=session, tool="prod_restart", approver="alice")
    result = gate.check(
        role="sre", tool="prod_restart", actor="sre-1", session=session
    )
    assert result.allowed is False


def test_allow_read_file(gate) -> None:
    for role in ("intern", "engineer", "sre"):
        result = gate.check(role=role, tool="read_file", actor="a")
        assert result.allowed is True
        assert result.decision == "allow"


def test_intern_denied_http_fetch_and_shell(gate) -> None:
    assert gate.check(role="intern", tool="http_fetch", actor="a").allowed is False
    assert gate.check(role="intern", tool="shell", actor="a").allowed is False


def test_engineer_allowed_http_fetch_and_shell(gate) -> None:
    assert gate.check(role="engineer", tool="http_fetch", actor="a").allowed is True
    assert gate.check(role="engineer", tool="shell", actor="a").allowed is True


def test_unknown_tool_denied(gate) -> None:
    result = gate.check(role="sre", tool="drop_database", actor="a")
    assert result.allowed is False


def test_budget_max_calls_per_session(tmp_path: Path) -> None:
    from agent_gate import Gate

    policy = tmp_path / "policy.yaml"
    policy.write_text(
        "roles: [intern]\n"
        "tools:\n"
        "  read_file:\n"
        "    allow: all\n"
        "budget:\n"
        "  max_calls_per_session: 1\n",
        encoding="utf-8",
    )
    gate = Gate(policy_path=policy, audit_path=tmp_path / "audit.jsonl")
    assert gate.check(role="intern", tool="read_file", actor="a", session="B").allowed
    gate.record(
        session="B",
        actor="a",
        tool="read_file",
        args={},
        decision="allow",
        role="intern",
    )
    over = gate.check(role="intern", tool="read_file", actor="a", session="B")
    assert over.allowed is False
    assert "budget" in over.reason.lower()
