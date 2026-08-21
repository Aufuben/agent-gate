from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_POLICY = ROOT / "policies" / "example.yaml"


def test_default_paths_are_absolute_and_policy_exists() -> None:
    from agent_gate.gui import default_audit_path, default_policy_path

    policy = Path(default_policy_path())
    audit = Path(default_audit_path())
    assert policy.is_absolute()
    assert audit.is_absolute()
    assert policy == EXAMPLE_POLICY.resolve()
    assert policy.is_file()
    assert audit.name == "audit.jsonl"


def test_abs_path_resolves_relative(tmp_path: Path, monkeypatch) -> None:
    from agent_gate.gui import abs_path

    monkeypatch.chdir(tmp_path)
    resolved = abs_path("./audit.jsonl")
    assert Path(resolved).is_absolute()
    assert Path(resolved) == (tmp_path / "audit.jsonl").resolve()


def test_new_session_id_is_unique() -> None:
    from agent_gate.gui import new_session_id

    a = new_session_id()
    b = new_session_id()
    assert a
    assert b
    assert a != b


def test_perform_check_intern_prod_restart_denied(tmp_path: Path) -> None:
    from agent_gate.gui import format_verdict, perform_check

    result = perform_check(
        policy_path=str(EXAMPLE_POLICY),
        audit_path=str(tmp_path / "audit.jsonl"),
        role="intern",
        tool="prod_restart",
        actor="实习生甲",
        session="sess-intern",
    )
    assert result.allowed is False
    assert result.decision == "deny"
    assert "intern" in result.reason
    text = format_verdict(result)
    assert text.startswith("拒绝")
    assert result.reason in text


def test_perform_approve_same_person_twice_marks_duplicate(tmp_path: Path) -> None:
    from agent_gate.gui import perform_approve

    audit = str(tmp_path / "audit.jsonl")
    first = perform_approve(
        audit_path=audit, session="S", tool="prod_restart", approver="alice"
    )
    assert first.duplicate is False
    assert first.count == 1
    second = perform_approve(
        audit_path=audit, session="S", tool="prod_restart", approver="alice"
    )
    assert second.duplicate is True
    assert second.count == 1
    assert "不算" in second.message


def test_pick_approver_prefers_first_new_name() -> None:
    from agent_gate.gui import pick_approver_to_submit

    assert pick_approver_to_submit("alice", "bob", ()) == "alice"
    assert pick_approver_to_submit("alice", "bob", ("alice",)) == "bob"
    assert pick_approver_to_submit("alice", "alice", ("alice",)) == "alice"
    assert pick_approver_to_submit("", "", ()) is None


def test_perform_check_sre_prod_restart_after_two_approvers(tmp_path: Path) -> None:
    from agent_gate.gui import format_verdict, perform_approve, perform_check

    audit = str(tmp_path / "audit.jsonl")
    session = "sess-sre"
    kwargs = dict(
        policy_path=str(EXAMPLE_POLICY),
        audit_path=audit,
        role="sre",
        tool="prod_restart",
        actor="值班sre",
        session=session,
    )
    before = perform_check(**kwargs)
    assert before.allowed is False
    perform_approve(audit_path=audit, session=session, tool="prod_restart", approver="alice")
    perform_approve(audit_path=audit, session=session, tool="prod_restart", approver="bob")
    after = perform_check(**kwargs)
    assert after.allowed is True
    assert after.decision == "allow"
    assert format_verdict(after).startswith("允许")


def test_perform_record_writes_decision(tmp_path: Path) -> None:
    from agent_gate.audit import AuditLog
    from agent_gate.gui import perform_check, perform_record

    audit = str(tmp_path / "audit.jsonl")
    result = perform_check(
        policy_path=str(EXAMPLE_POLICY),
        audit_path=audit,
        role="intern",
        tool="prod_restart",
        actor="实习生甲",
        session="sess-r",
    )
    row = perform_record(
        audit_path=audit,
        session="sess-r",
        actor="实习生甲",
        tool="prod_restart",
        decision=result.decision,
        role="intern",
        reason=result.reason,
    )
    assert row["decision"] == "deny"
    decisions = AuditLog(audit).last_decisions(limit=5)
    assert decisions[-1]["tool"] == "prod_restart"
    assert decisions[-1]["decision"] == "deny"


def test_capture_demo_writes_expected_lines(tmp_path: Path) -> None:
    from agent_gate.demo import EXIT_OK
    from agent_gate.gui import capture_demo

    code, output = capture_demo(str(EXAMPLE_POLICY), str(tmp_path / "audit.jsonl"))
    assert code == EXIT_OK
    assert "demo done" in output
