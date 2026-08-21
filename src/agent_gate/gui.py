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

HOW_TO = (
    "这是拦截 Agent 工具调用的门。\n"
    "先检查，再执行；本页不真正重启生产。\n"
    "写操作要两个不同的人批准。\n"
    "同一人点两次批准不算两票。\n"
    "策略文件和审计日志使用本机绝对路径。点「浏览」会打开系统文件框。"
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


def format_verdict(result: CheckResult) -> str:
    title = "允许" if result.allowed else "拒绝"
    lines = [title, f"原因：{result.reason}"]
    if result.approvals_needed:
        lines.append(f"还差 {result.approvals_needed} 个不同审批人")
    if result.approvers:
        lines.append("已有审批人：" + "、".join(result.approvers))
    return "\n".join(lines)


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
        "how_to": [line for line in HOW_TO.splitlines() if line],
    }


def check_to_dict(result: CheckResult, audit_path: str) -> dict[str, Any]:
    data = result.as_dict()
    data["ok"] = True
    data["title"] = "允许" if result.allowed else "拒绝"
    data["verdict"] = format_verdict(result)
    data["recent"] = recent_events_text(audit_path)
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
            result = perform_check(
                policy_path=policy,
                audit_path=audit,
                role=str(payload.get("role") or ""),
                tool=str(payload.get("tool") or ""),
                actor=str(payload.get("actor") or "") or None,
                session=str(payload.get("session") or "") or None,
            )
            return 200, check_to_dict(result, audit)
        if path == "/api/approve":
            audit = str(payload.get("audit_path") or defaults.get("audit_path") or "")
            session = str(payload.get("session") or "").strip()
            tool = str(payload.get("tool") or "").strip()
            if not session:
                return 400, {"ok": False, "error": "请填写会话 ID。"}
            existing = existing_approvers(audit, session, tool)
            name = pick_approver_to_submit(
                str(payload.get("approver1") or payload.get("approver") or ""),
                str(payload.get("approver2") or ""),
                existing,
            )
            if not name:
                return 400, {"ok": False, "error": "请填写审批人1 或 审批人2。"}
            outcome = perform_approve(
                audit_path=audit, session=session, tool=tool, approver=name
            )
            data = approve_to_dict(outcome)
            data["recent"] = recent_events_text(audit)
            policy = str(payload.get("policy_path") or defaults.get("policy_path") or "")
            role = str(payload.get("role") or "")
            if policy and role and tool:
                checked = perform_check(
                    policy_path=policy,
                    audit_path=audit,
                    role=role,
                    tool=tool,
                    actor=str(payload.get("actor") or "") or None,
                    session=session,
                )
                data["check"] = check_to_dict(checked, audit)
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
