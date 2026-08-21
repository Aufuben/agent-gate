from __future__ import annotations

import argparse
from datetime import date, datetime
from pathlib import Path

from agent_gate.keys import PROVIDERS
from agent_gate.report import default_date_range, format_table, query_usage


def _parse_day(text: str) -> date:
    return datetime.strptime(text, "%Y-%m-%d").date()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agent-gate",
        description="查询 API Key 额度：OpenRouter / DeepSeek / OpenAI。",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    usage = sub.add_parser("usage", help="Query per-key usage and quota")
    usage.add_argument("--keys-file", required=True, help="One key per line (gitignored)")
    usage.add_argument("--from", dest="from_date", default=None, help="YYYY-MM-DD, default last 30 days")
    usage.add_argument("--to", dest="to_date", default=None, help="YYYY-MM-DD")
    usage.add_argument(
        "--providers",
        default="openrouter,deepseek,openai",
        help="Comma list: openrouter,deepseek,openai",
    )

    gui = sub.add_parser("gui", help="Local page: paste keys, 统计额度")
    gui.add_argument("--host", default="127.0.0.1")
    gui.add_argument("--port", type=int, default=8765)
    gui.add_argument("--no-browser", action="store_true")

    legacy = sub.add_parser("legacy", help=argparse.SUPPRESS)
    legacy_sub = legacy.add_subparsers(dest="legacy_cmd", required=True)
    check = legacy_sub.add_parser("check")
    check.add_argument("--policy", required=True)
    check.add_argument("--role", required=True)
    check.add_argument("--tool", required=True)
    check.add_argument("--actor", default="")
    check.add_argument("--session", default=None)
    check.add_argument("--audit", default="audit.jsonl")
    return parser


def _run_usage(args: argparse.Namespace) -> int:
    path = Path(args.keys_file).expanduser()
    if not path.is_file():
        print(f"usage: keys file not found: {path}", flush=True)
        return 2
    text = path.read_text(encoding="utf-8")
    start, end = default_date_range()
    if args.from_date:
        start = _parse_day(args.from_date)
    if args.to_date:
        end = _parse_day(args.to_date)
    providers = tuple(item.strip() for item in str(args.providers).split(",") if item.strip()) or PROVIDERS
    report = query_usage(
        text=text,
        from_date=start,
        to_date=end,
        providers=providers,
    )
    print(format_table(report), flush=True)
    return 0


def _run_legacy(args: argparse.Namespace) -> int:
    import json

    from agent_gate.legacy import Gate

    if args.legacy_cmd == "check":
        gate = Gate(policy_path=args.policy, audit_path=args.audit)
        result = gate.check(
            role=args.role,
            tool=args.tool,
            actor=args.actor or None,
            session=args.session,
        )
        print(json.dumps(result.as_dict(), ensure_ascii=False), flush=True)
        return 0 if result.allowed else 1
    return 2


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        code = exc.code
        if code is None:
            return 0
        return int(code)

    if args.cmd == "usage":
        return _run_usage(args)
    if args.cmd == "gui":
        from agent_gate.gui import run_gui

        return run_gui(host=args.host, port=args.port, open_browser=not args.no_browser)
    if args.cmd == "legacy":
        return _run_legacy(args)

    parser.print_help()
    return 2


def console_main() -> None:
    raise SystemExit(main())


if __name__ == "__main__":
    console_main()
