from __future__ import annotations

import argparse
import json
from pathlib import Path

from agent_gate.demo import run_demo
from agent_gate.gate import Gate


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agent-gate",
        description="Tool-call control plane: check, dual-control, audit.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    check = sub.add_parser("check", help="Evaluate policy for a role+tool")
    check.add_argument("--policy", required=True)
    check.add_argument("--role", required=True)
    check.add_argument("--tool", required=True)
    check.add_argument("--actor", default="")
    check.add_argument("--session", default=None)
    check.add_argument("--audit", default="audit.jsonl")

    record = sub.add_parser("record", help="Append a decision to the audit log")
    record.add_argument("--session", required=True)
    record.add_argument("--actor", required=True)
    record.add_argument("--tool", required=True)
    record.add_argument("--args", default="{}")
    record.add_argument("--decision", required=True, choices=["allow", "deny"])
    record.add_argument("--role", default="")
    record.add_argument("--reason", default="")
    record.add_argument("--audit", default="audit.jsonl")

    approve = sub.add_parser("approve", help="Record an approver id for session+tool")
    approve.add_argument("--session", required=True)
    approve.add_argument("--tool", required=True)
    approve.add_argument("--approver", required=True)
    approve.add_argument("--audit", default="audit.jsonl")

    export = sub.add_parser("export-audit", help="Write audit JSONL to CSV")
    export.add_argument("--from", dest="from_ts", required=True)
    export.add_argument("--out", required=True)
    export.add_argument("--audit", default="audit.jsonl")

    demo = sub.add_parser("demo", help="Dummy agent: read_file ok, prod_restart dual-control")
    demo.add_argument("--policy", default="policies/example.yaml")
    demo.add_argument("--audit", default="audit.jsonl")

    gui = sub.add_parser("gui", help="Local page: who, what, can they do it")
    gui.add_argument("--policy", default="policies/example.yaml")
    gui.add_argument("--audit", default="audit.jsonl")
    gui.add_argument("--host", default="127.0.0.1")
    gui.add_argument("--port", type=int, default=8765)
    gui.add_argument("--no-browser", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        code = exc.code
        if code is None:
            return 0
        return int(code)

    if args.cmd == "check":
        gate = Gate(policy_path=args.policy, audit_path=args.audit)
        result = gate.check(
            role=args.role,
            tool=args.tool,
            actor=args.actor or None,
            session=args.session,
        )
        print(json.dumps(result.as_dict(), ensure_ascii=False), flush=True)
        return 0 if result.allowed else 1

    if args.cmd == "record":
        gate = Gate(policy_path=None, audit_path=args.audit)
        row = gate.record(
            session=args.session,
            actor=args.actor,
            tool=args.tool,
            args=args.args,
            decision=args.decision,
            role=args.role or None,
            reason=args.reason or None,
        )
        print(json.dumps(row, ensure_ascii=False), flush=True)
        return 0

    if args.cmd == "approve":
        gate = Gate(policy_path=None, audit_path=args.audit)
        row = gate.approve(
            session=args.session, tool=args.tool, approver=args.approver
        )
        print(json.dumps(row, ensure_ascii=False), flush=True)
        return 0

    if args.cmd == "export-audit":
        gate = Gate(policy_path=None, audit_path=args.audit)
        out = gate.export_audit(from_ts=args.from_ts, out=args.out)
        print(str(Path(out)), flush=True)
        return 0

    if args.cmd == "demo":
        return run_demo(policy_path=args.policy, audit_path=args.audit)

    if args.cmd == "gui":
        from agent_gate.gui import run_gui

        return run_gui(
            policy_path=args.policy,
            audit_path=args.audit,
            host=args.host,
            port=args.port,
            open_browser=not args.no_browser,
        )

    parser.print_help()
    return 2


def console_main() -> None:
    raise SystemExit(main())


if __name__ == "__main__":
    console_main()
