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
    assert text.startswith("不能")
    assert "实习生不能重启生产" in text


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
    assert format_verdict(after).startswith("能")


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


def test_page_html_is_simple_without_gradient_or_emoji() -> None:
    from agent_gate.gui import page_html

    html = page_html()
    assert "能不能做" in html
    assert "实习生" in html
    assert "重启生产" in html
    assert "高级" in html
    assert "浏览" in html
    assert "alice" in html
    assert "bob" in html
    assert "gradient" not in html.lower()
    assert "emoji" not in html.lower()
    assert "\U0001f389" not in html
    assert html.count("input") >= 2
    assert "details" in html


def test_dispatch_check_intern_prod_restart_denied(tmp_path: Path) -> None:
    from agent_gate.gui import dispatch_api

    status, data = dispatch_api(
        "/api/check",
        {
            "policy_path": str(EXAMPLE_POLICY),
            "audit_path": str(tmp_path / "audit.jsonl"),
            "role": "intern",
            "tool": "prod_restart",
            "actor": "实习生甲",
            "session": "sess-http",
        },
    )
    assert status == 200
    assert data["allowed"] is False
    assert data["title"] == "不能"
    assert data["needs_dual"] is False
    assert "实习生不能重启生产" in data["reason_human"]
    assert data.get("recorded") is not None
    assert data["recorded"]["decision"] == "deny"


def test_dispatch_browse_uses_injected_picker() -> None:
    from agent_gate.gui import dispatch_api

    status, data = dispatch_api(
        "/api/browse",
        {"kind": "policy", "initial": ""},
        browse_fn=lambda kind, initial: "/abs/policy.yaml",
    )
    assert status == 200
    assert data["path"] == "/abs/policy.yaml"


def test_http_server_serves_page_and_check(tmp_path: Path) -> None:
    import json
    from http.client import HTTPConnection
    from threading import Thread

    from agent_gate.gui import make_server

    server = make_server(
        policy_path=str(EXAMPLE_POLICY),
        audit_path=str(tmp_path / "audit.jsonl"),
        host="127.0.0.1",
        port=0,
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        conn = HTTPConnection("127.0.0.1", server.port, timeout=5)
        conn.request("GET", "/")
        res = conn.getresponse()
        body = res.read().decode("utf-8")
        assert res.status == 200
        assert "能不能做" in body
        assert "高级" in body

        payload = json.dumps(
            {
                "policy_path": str(EXAMPLE_POLICY),
                "audit_path": str(tmp_path / "audit.jsonl"),
                "role": "intern",
                "tool": "prod_restart",
                "actor": "甲",
                "session": "s1",
            }
        ).encode("utf-8")
        conn.request(
            "POST",
            "/api/check",
            payload,
            {"Content-Type": "application/json"},
        )
        checked = conn.getresponse()
        data = json.loads(checked.read().decode("utf-8"))
        assert checked.status == 200
        assert data["allowed"] is False
        assert data["title"] == "不能"
    finally:
        try:
            conn.close()
        except Exception:
            pass
        server.shutdown()
        thread.join(timeout=2)


def test_human_reason_intern_cannot_restart() -> None:
    from agent_gate.gui import human_reason, needs_dual, perform_check, verdict_title

    result = perform_check(
        policy_path=str(EXAMPLE_POLICY),
        audit_path="unused.jsonl",
        role="intern",
        tool="prod_restart",
        actor=None,
        session="s",
    )
    assert verdict_title(result) == "不能"
    assert needs_dual(result) is False
    assert human_reason(result) == "实习生不能重启生产。"


def test_dispatch_sre_restart_needs_two_people_without_recording(tmp_path: Path) -> None:
    from agent_gate.audit import AuditLog
    from agent_gate.gui import dispatch_api

    audit = str(tmp_path / "audit.jsonl")
    status, data = dispatch_api(
        "/api/check",
        {
            "policy_path": str(EXAMPLE_POLICY),
            "audit_path": audit,
            "role": "sre",
            "tool": "prod_restart",
            "session": "sess-dual",
        },
    )
    assert status == 200
    assert data["title"] == "要两个人批"
    assert data["needs_dual"] is True
    assert "要两个人同意" in data["reason_human"]
    assert data.get("recorded") is None
    assert list(AuditLog(audit).iter_events()) == []


def test_dispatch_two_consents_then_allowed_and_recorded(tmp_path: Path) -> None:
    from agent_gate.gui import dispatch_api

    audit = str(tmp_path / "audit.jsonl")
    body = {
        "policy_path": str(EXAMPLE_POLICY),
        "audit_path": audit,
        "role": "sre",
        "tool": "prod_restart",
        "session": "sess-ok",
    }
    dispatch_api("/api/check", body)
    first = dispatch_api("/api/approve", {**body, "approver": "alice"})
    assert first[0] == 200
    assert first[1]["check"]["needs_dual"] is True
    assert first[1]["check"].get("recorded") is None
    second = dispatch_api("/api/approve", {**body, "approver": "bob"})
    assert second[0] == 200
    assert second[1]["check"]["allowed"] is True
    assert second[1]["check"]["title"] == "能"
    assert second[1]["check"]["needs_dual"] is False
    assert second[1]["check"].get("recorded") is not None
    assert "已经同意" in second[1]["check"]["reason_human"]

