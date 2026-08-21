from __future__ import annotations

import io
import json
import uuid
from contextlib import redirect_stdout
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent_gate.audit import AuditLog
from agent_gate.gate import CheckResult, Gate

ROLES = ("intern", "engineer", "sre")
TOOLS = ("read_file", "http_fetch", "shell", "prod_restart")
ROLE_ZH = {"intern": "实习生", "engineer": "工程师", "sre": "SRE"}
TOOL_ZH = {
    "read_file": "读文件",
    "http_fetch": "访问外网",
    "shell": "执行命令",
    "prod_restart": "重启生产",
}
ROLE_OPTIONS = tuple({"id": key, "label": ROLE_ZH[key]} for key in ROLES)
TOOL_OPTIONS = tuple({"id": key, "label": TOOL_ZH[key]} for key in TOOLS)

HOW_TO = (
    "选好身份和要做的事，点「能不能做」。\n"
    "写操作要两个不同的人同意；同一人点两次不算。\n"
    "策略和审计路径在「高级」里，默认用自带的 example.yaml。"
)

STATIC_DIR = Path(__file__).resolve().parent / "static"


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def abs_path(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        return ""
    return str(Path(text).expanduser().resolve())


def default_policy_path() -> str:
    return str((repo_root() / "policies" / "example.yaml").resolve())


def default_audit_path() -> str:
    return str(Path("audit.jsonl").expanduser().resolve())


def resolve_policy_path(raw: str) -> str:
    text = (raw or "").strip() or "policies/example.yaml"
    path = Path(text).expanduser()
    if path.is_file():
        return str(path.resolve())
    bundled = Path(default_policy_path())
    if not path.is_absolute() and bundled.is_file():
        return str(bundled)
    return str(path.resolve())


def new_session_id() -> str:
    return f"sess-{uuid.uuid4().hex[:12]}"


def who_zh(role: str) -> str:
    return ROLE_ZH.get(role, role)


def what_zh(tool: str) -> str:
    return TOOL_ZH.get(tool, tool)


def default_actor(role: str, actor: str | None = None) -> str:
    text = (actor or "").strip()
    return text or who_zh(role)


def needs_dual(result: CheckResult) -> bool:
    return (not result.allowed) and int(result.approvals_needed or 0) > 0


def verdict_title(result: CheckResult) -> str:
    if result.allowed:
        return "能"
    if needs_dual(result):
        return "要两个人批"
    return "不能"


def human_reason(result: CheckResult) -> str:
    who = who_zh(result.role)
    what = what_zh(result.tool)
    if needs_dual(result):
        have = list(result.approvers)
        if not have:
            return f"{what}要两个人同意。现在还没有人批。"
        if len(have) == 1:
            return f"{what}要两个人同意。现在只有 {have[0]} 批了。"
        return f"{what}还差 {result.approvals_needed} 个人同意。"
    if result.allowed:
        if result.approvers:
            names = "、".join(result.approvers)
            return f"{who}可以{what}。{names} 已经同意。"
        return f"{who}可以{what}。"
    reason = result.reason or ""
    if "unknown role" in reason:
        return f"不认识这个身份「{who}」。"
    if "unknown tool" in reason:
        return f"没有这项操作「{what}」。"
    if "budget exceeded" in reason:
        return "这个会话的次数已经用完。"
    if "no allow rule" in reason:
        return f"策略没有允许任何人{what}。"
    return f"{who}不能{what}。"


def format_verdict(result: CheckResult) -> str:
    return f"{verdict_title(result)}\n{human_reason(result)}"


def perform_check(
    policy_path: str,
    audit_path: str,
    role: str,
    tool: str,
    actor: str | None,
    session: str | None,
) -> CheckResult:
    gate = Gate(policy_path=abs_path(policy_path) or policy_path, audit_path=abs_path(audit_path) or audit_path)
    return gate.check(
        role=role,
        tool=tool,
        actor=(actor or None),
        session=(session or None),
    )


@dataclass(frozen=True)
class ApproveResult:
    duplicate: bool
    count: int
    unique_approvers: tuple[str, ...]
    dual_control_met: bool
    message: str
    row: dict[str, Any]


def existing_approvers(audit_path: str, session: str, tool: str) -> tuple[str, ...]:
    return AuditLog(abs_path(audit_path) or audit_path).unique_approvers(session, tool)


def pick_approver_to_submit(
    approver1: str, approver2: str, existing: tuple[str, ...]
) -> str | None:
    a1 = (approver1 or "").strip()
    a2 = (approver2 or "").strip()
    seen = set(existing)
    for name in (a1, a2):
        if name and name not in seen:
            return name
    filled = [name for name in (a1, a2) if name]
    if not filled:
        return None
    return filled[-1]


def perform_approve(
    audit_path: str, session: str, tool: str, approver: str
) -> ApproveResult:
    name = str(approver).strip()
    if not name:
        raise ValueError("审批人不能为空")
    session_id = str(session).strip()
    if not session_id:
        raise ValueError("会话 ID 不能为空")
    tool_name = str(tool).strip()
    if not tool_name:
        raise ValueError("工具不能为空")

    gate = Gate(policy_path=None, audit_path=abs_path(audit_path) or audit_path)
    duplicate = name in gate.audit.unique_approvers(session_id, tool_name)
    row = gate.approve(session=session_id, tool=tool_name, approver=name)
    count = int(row["count"])
    unique = tuple(str(x) for x in row["unique_approvers"])
    met = bool(row["dual_control_met"])
    if duplicate:
        message = (
            f"同一人「{name}」点两次不算两票。"
            f"当前不同审批人 {count}/2"
            + (f"：{'、'.join(unique)}" if unique else "")
        )
    else:
        message = f"已记录审批人「{name}」。当前不同审批人 {count}/2"
        if met:
            message += "（已凑齐两人，可再点检查）"
    return ApproveResult(
        duplicate=duplicate,
        count=count,
        unique_approvers=unique,
        dual_control_met=met,
        message=message,
        row=row,
    )


def perform_record(
    audit_path: str,
    session: str,
    actor: str,
    tool: str,
    decision: str,
    role: str | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    gate = Gate(policy_path=None, audit_path=abs_path(audit_path) or audit_path)
    return gate.record(
        session=session,
        actor=actor,
        tool=tool,
        args={},
        decision=decision,
        role=role,
        reason=reason,
    )


def recent_events_text(audit_path: str, limit: int = 20) -> str:
    path = Path(abs_path(audit_path) or audit_path)
    if not path.is_file():
        return f"审计文件尚不存在：{path}"
    rows = list(AuditLog(path).iter_events())[-limit:]
    if not rows:
        return f"审计文件为空：{path}"
    lines = [json.dumps(row, ensure_ascii=False) for row in reversed(rows)]
    return "\n".join(lines)


def capture_demo(policy_path: str, audit_path: str) -> tuple[int, str]:
    buf = io.StringIO()
    with redirect_stdout(buf):
        from agent_gate.demo import run_demo

        code = run_demo(policy_path=policy_path, audit_path=audit_path)
    return code, buf.getvalue()


def page_html() -> str:
    return (STATIC_DIR / "index.html").read_text(encoding="utf-8")


def bootstrap_state(policy_path: str, audit_path: str) -> dict[str, Any]:
    return {
        "ok": True,
        "policy_path": resolve_policy_path(policy_path),
        "audit_path": abs_path(audit_path) or default_audit_path(),
        "session": new_session_id(),
        "roles": list(ROLES),
        "tools": list(TOOLS),
        "role_options": [dict(item) for item in ROLE_OPTIONS],
        "tool_options": [dict(item) for item in TOOL_OPTIONS],
        "how_to": [line for line in HOW_TO.splitlines() if line],
    }


def maybe_auto_record(
    result: CheckResult,
    audit_path: str,
    actor: str | None = None,
) -> dict[str, Any] | None:
    if needs_dual(result):
        return None
    session = (result.session or "").strip()
    if not session:
        return None
    return perform_record(
        audit_path=audit_path,
        session=session,
        actor=default_actor(result.role, actor),
        tool=result.tool,
        decision=result.decision,
        role=result.role,
        reason=result.reason,
    )


def check_to_dict(
    result: CheckResult,
    audit_path: str,
    recorded: dict[str, Any] | None = None,
) -> dict[str, Any]:
    data = result.as_dict()
    data["ok"] = True
    data["title"] = verdict_title(result)
    data["reason_human"] = human_reason(result)
    data["needs_dual"] = needs_dual(result)
    data["verdict"] = format_verdict(result)
    data["recent"] = recent_events_text(audit_path)
    if recorded is not None:
        data["recorded"] = recorded
    return data


def approve_to_dict(outcome: ApproveResult) -> dict[str, Any]:
    return {
        "ok": True,
        "duplicate": outcome.duplicate,
        "count": outcome.count,
        "unique_approvers": list(outcome.unique_approvers),
        "dual_control_met": outcome.dual_control_met,
        "message": outcome.message,
        "row": outcome.row,
    }


def native_browse(kind: str, initial: str = "") -> str:
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    try:
        root.wm_attributes("-topmost", True)
    except tk.TclError:
        pass
    root.update()
    start = Path(initial) if (initial or "").strip() else Path.cwd()
    parent = start.parent if start.suffix else start
    if not parent.exists():
        parent = Path.cwd()
    try:
        if kind == "policy":
            chosen = filedialog.askopenfilename(
                title="选择策略文件",
                filetypes=[("YAML", "*.yaml"), ("YAML", "*.yml"), ("全部", "*")],
                initialdir=str(parent),
            )
        else:
            chosen = filedialog.asksaveasfilename(
                title="选择审计日志",
                defaultextension=".jsonl",
                filetypes=[("JSONL", "*.jsonl"), ("全部", "*")],
                initialdir=str(parent),
                initialfile=start.name if start.suffix else "audit.jsonl",
            )
    finally:
        root.destroy()
    return abs_path(chosen) if chosen else ""


def dispatch_api(
    path: str,
    body: dict[str, Any] | None = None,
    *,
    defaults: dict[str, str] | None = None,
    browse_fn: Any = None,
) -> tuple[int, dict[str, Any]]:
    payload = body or {}
    defaults = defaults or {}
    try:
        if path == "/api/state":
            return 200, bootstrap_state(
                defaults.get("policy_path", "policies/example.yaml"),
                defaults.get("audit_path", "audit.jsonl"),
            )
        if path == "/api/session":
            return 200, {"ok": True, "session": new_session_id()}
        if path == "/api/check":
            policy = str(payload.get("policy_path") or defaults.get("policy_path") or "")
            audit = str(payload.get("audit_path") or defaults.get("audit_path") or "")
            role = str(payload.get("role") or "")
            actor = str(payload.get("actor") or "") or None
            session = str(payload.get("session") or "").strip() or new_session_id()
            result = perform_check(
                policy_path=policy,
                audit_path=audit,
                role=role,
                tool=str(payload.get("tool") or ""),
                actor=default_actor(role, actor),
                session=session,
            )
            recorded = maybe_auto_record(result, audit, actor)
            return 200, check_to_dict(result, audit, recorded=recorded)
        if path == "/api/approve":
            audit = str(payload.get("audit_path") or defaults.get("audit_path") or "")
            session = str(payload.get("session") or "").strip() or new_session_id()
            tool = str(payload.get("tool") or "").strip()
            name = str(payload.get("approver") or "").strip()
            if not name:
                existing = existing_approvers(audit, session, tool)
                name = pick_approver_to_submit(
                    str(payload.get("approver1") or ""),
                    str(payload.get("approver2") or ""),
                    existing,
                ) or ""
            if not name:
                return 400, {"ok": False, "error": "请填写同意的人。"}
            outcome = perform_approve(
                audit_path=audit, session=session, tool=tool, approver=name
            )
            data = approve_to_dict(outcome)
            data["recent"] = recent_events_text(audit)
            policy = str(payload.get("policy_path") or defaults.get("policy_path") or "")
            role = str(payload.get("role") or "")
            if policy and role and tool:
                actor = str(payload.get("actor") or "") or None
                checked = perform_check(
                    policy_path=policy,
                    audit_path=audit,
                    role=role,
                    tool=tool,
                    actor=default_actor(role, actor),
                    session=session,
                )
                recorded = maybe_auto_record(checked, audit, actor)
                data["check"] = check_to_dict(checked, audit, recorded=recorded)
            return 200, data
        if path == "/api/record":
            audit = str(payload.get("audit_path") or defaults.get("audit_path") or "")
            row = perform_record(
                audit_path=audit,
                session=str(payload.get("session") or ""),
                actor=str(payload.get("actor") or ""),
                tool=str(payload.get("tool") or ""),
                decision=str(payload.get("decision") or ""),
                role=str(payload.get("role") or "") or None,
                reason=str(payload.get("reason") or "") or None,
            )
            return 200, {"ok": True, "row": row, "recent": recent_events_text(audit)}
        if path == "/api/demo":
            policy = str(payload.get("policy_path") or defaults.get("policy_path") or "")
            audit = str(payload.get("audit_path") or defaults.get("audit_path") or "")
            code, output = capture_demo(policy, audit)
            return 200, {
                "ok": True,
                "code": code,
                "output": output,
                "recent": recent_events_text(audit),
            }
        if path == "/api/browse":
            kind = str(payload.get("kind") or "policy")
            picker = browse_fn or native_browse
            chosen = picker(kind, str(payload.get("initial") or ""))
            return 200, {"ok": True, "path": chosen}
        if path == "/api/recent":
            audit = str(payload.get("audit_path") or defaults.get("audit_path") or "")
            return 200, {"ok": True, "recent": recent_events_text(audit)}
        return 404, {"ok": False, "error": f"unknown path {path}"}
    except Exception as exc:  # noqa: BLE001 — return load/IO errors to the page
        return 400, {"ok": False, "error": str(exc)}


class GateHTTPServer:
    """Thin wrapper so tests can start/stop a local server without opening a browser."""

    def __init__(self, server: Any) -> None:
        self.server = server

    @property
    def url(self) -> str:
        host, port = self.server.server_address[:2]
        return f"http://{host}:{port}/"

    @property
    def port(self) -> int:
        return int(self.server.server_address[1])

    def serve_forever(self) -> None:
        self.server.serve_forever()

    def shutdown(self) -> None:
        self.server.shutdown()
        self.server.server_close()


def make_server(
    policy_path: str = "policies/example.yaml",
    audit_path: str = "audit.jsonl",
    host: str = "127.0.0.1",
    port: int = 8765,
) -> GateHTTPServer:
    from http.server import BaseHTTPRequestHandler, HTTPServer

    defaults = {
        "policy_path": resolve_policy_path(policy_path),
        "audit_path": abs_path(audit_path) or default_audit_path(),
    }
    html = page_html()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args: Any) -> None:
            return

        def _send(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(body)
            self.close_connection = True

        def _read_json(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0:
                return {}
            raw = self.rfile.read(length)
            if not raw:
                return {}
            data = json.loads(raw.decode("utf-8"))
            if not isinstance(data, dict):
                raise ValueError("JSON body must be an object")
            return data

        def do_GET(self) -> None:  # noqa: N802
            route = self.path.split("?", 1)[0]
            if route in {"/", "/index.html"}:
                payload = html.encode("utf-8")
                self._send(200, payload, "text/html; charset=utf-8")
                return
            if route.startswith("/api/"):
                status, data = dispatch_api(route, {}, defaults=defaults)
                blob = json.dumps(data, ensure_ascii=False).encode("utf-8")
                self._send(status, blob, "application/json; charset=utf-8")
                return
            self._send(404, b"not found", "text/plain; charset=utf-8")

        def do_POST(self) -> None:  # noqa: N802
            route = self.path.split("?", 1)[0]
            try:
                body = self._read_json()
            except (ValueError, json.JSONDecodeError) as exc:
                blob = json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False).encode(
                    "utf-8"
                )
                self._send(400, blob, "application/json; charset=utf-8")
                return
            status, data = dispatch_api(route, body, defaults=defaults)
            blob = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self._send(status, blob, "application/json; charset=utf-8")

    try:
        httpd = HTTPServer((host, port), Handler)
    except OSError:
        if port == 0:
            raise
        httpd = HTTPServer((host, 0), Handler)
    return GateHTTPServer(httpd)


def run_gui(
    policy_path: str = "policies/example.yaml",
    audit_path: str = "audit.jsonl",
    host: str = "127.0.0.1",
    port: int = 8765,
    open_browser: bool = True,
) -> int:
    import threading
    import time
    import webbrowser

    server = make_server(
        policy_path=policy_path, audit_path=audit_path, host=host, port=port
    )
    url = server.url
    print(f"agent-gate gui  {url}", flush=True)
    if open_browser:
        def _open() -> None:
            time.sleep(0.25)
            webbrowser.open(url)

        threading.Thread(target=_open, daemon=True).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped", flush=True)
    finally:
        server.server.server_close()
    return 0
