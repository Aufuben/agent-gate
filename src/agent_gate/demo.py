from __future__ import annotations

from pathlib import Path

from agent_gate.gate import Gate

EXIT_OK = 0
EXIT_UNEXPECTED = 1
EXIT_USAGE = 2


def run_demo(
    policy_path: str | Path = "policies/example.yaml",
    audit_path: str | Path = "audit.jsonl",
) -> int:
    """Dummy agent: read_file is allowed; prod_restart waits for two distinct approvers."""
    path = Path(policy_path)
    if not path.is_file():
        print(f"usage: policy not found: {path}", flush=True)
        return EXIT_USAGE

    try:
        gate = Gate(policy_path=path, audit_path=audit_path)
    except Exception as exc:  # noqa: BLE001 — surface load errors as usage
        print(f"usage: failed to load policy: {exc}", flush=True)
        return EXIT_USAGE

    session = "demo-session"

    def step(
        role: str,
        tool: str,
        actor: str,
        expect_allow: bool,
        session_id: str | None = session,
    ) -> bool:
        result = gate.check(
            role=role, tool=tool, actor=actor, session=session_id
        )
        gate.record(
            session=session_id or "none",
            actor=actor,
            tool=tool,
            args={},
            decision=result.decision,
            role=role,
            reason=result.reason,
        )
        ok = result.allowed is expect_allow
        mark = "ok" if ok else "UNEXPECTED"
        print(
            f"{mark} {result.decision} role={role} tool={tool} "
            f"expect_allow={expect_allow} reason={result.reason}",
            flush=True,
        )
        return ok

    if not step("intern", "read_file", "demo-intern", True):
        return EXIT_UNEXPECTED
    if not step("intern", "prod_restart", "demo-intern", False):
        return EXIT_UNEXPECTED
    if not step("sre", "prod_restart", "demo-sre", False):
        return EXIT_UNEXPECTED

    first = gate.approve(session=session, tool="prod_restart", approver="alice")
    print(f"ok approve alice unique={first['count']}", flush=True)
    if not step("sre", "prod_restart", "demo-sre", False):
        return EXIT_UNEXPECTED

    dup = gate.approve(session=session, tool="prod_restart", approver="alice")
    print(f"ok approve alice again unique={dup['count']}", flush=True)
    if dup["count"] != 1:
        print("UNEXPECTED same approver counted twice", flush=True)
        return EXIT_UNEXPECTED
    if not step("sre", "prod_restart", "demo-sre", False):
        return EXIT_UNEXPECTED

    second = gate.approve(session=session, tool="prod_restart", approver="bob")
    print(f"ok approve bob unique={second['count']}", flush=True)
    if not step("sre", "prod_restart", "demo-sre", True):
        return EXIT_UNEXPECTED

    print("demo done", flush=True)
    return EXIT_OK
