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
    "先检查，再执行；本窗口不真正重启生产。\n"
    "写操作要两个不同的人批准。\n"
    "同一人点两次批准不算两票。\n"
    "下面按编号填写路径、角色、工具后点按钮。"
)


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


def run_gui(policy_path: str = "policies/example.yaml", audit_path: str = "audit.jsonl") -> int:
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox, ttk
    except ImportError as exc:
        print(f"gui unavailable: tkinter is not installed ({exc})", flush=True)
        return 2

    try:
        root = tk.Tk()
    except tk.TclError as exc:
        print(f"gui unavailable: {exc}", flush=True)
        return 2

    root.title("agent-gate")
    root.minsize(700, 640)
    root.geometry("840x860")

    policy_var = tk.StringVar(value=resolve_policy_path(policy_path))
    audit_var = tk.StringVar(value=abs_path(audit_path) or default_audit_path())
    role_var = tk.StringVar(value="intern")
    tool_var = tk.StringVar(value="read_file")
    actor_var = tk.StringVar(value="")
    session_var = tk.StringVar(value=new_session_id())
    approver1_var = tk.StringVar(value="")
    approver2_var = tk.StringVar(value="")

    last_result: dict[str, CheckResult | None] = {"value": None}

    style = ttk.Style()
    try:
        style.theme_use("aqua")
    except tk.TclError:
        pass
    style.configure("HowTo.TLabel", foreground="#1f2937")
    style.configure("Step.TLabel", foreground="#111827")
    style.configure("Hint.TLabel", foreground="#4b5563")
    style.configure("Check.TButton", font=("", 15, "bold"), padding=(12, 8))
    style.configure("Action.TButton", padding=(8, 6))

    outer = ttk.Frame(root, padding=14)
    outer.pack(fill="both", expand=True)
    outer.columnconfigure(0, weight=1)
    outer.rowconfigure(1, weight=1)
    outer.rowconfigure(2, weight=1)

    how = ttk.LabelFrame(outer, text="怎么用", padding=8)
    how.grid(row=0, column=0, sticky="ew")
    ttk.Label(how, text=HOW_TO, style="HowTo.TLabel", justify="left").pack(anchor="w")

    canvas_hold = ttk.Frame(outer)
    canvas_hold.grid(row=1, column=0, sticky="nsew", pady=(10, 8))
    canvas_hold.columnconfigure(0, weight=1)
    canvas_hold.rowconfigure(0, weight=1)
    canvas = tk.Canvas(canvas_hold, highlightthickness=0, borderwidth=0)
    canvas_scroll = ttk.Scrollbar(canvas_hold, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=canvas_scroll.set)
    canvas.grid(row=0, column=0, sticky="nsew")
    canvas_scroll.grid(row=0, column=1, sticky="ns")

    steps = ttk.Frame(canvas)
    steps.columnconfigure(1, weight=1)
    steps_window = canvas.create_window((0, 0), window=steps, anchor="nw")

    def _sync_scroll(_event: object | None = None) -> None:
        canvas.configure(scrollregion=canvas.bbox("all"))
        canvas.itemconfigure(steps_window, width=canvas.winfo_width())

    steps.bind("<Configure>", _sync_scroll)
    canvas.bind("<Configure>", _sync_scroll)

    def _on_mousewheel(event: tk.Event) -> None:
        canvas.yview_scroll(int(-1 * event.delta), "units")

    canvas.bind("<Enter>", lambda _e: canvas.bind_all("<MouseWheel>", _on_mousewheel))
    canvas.bind("<Leave>", lambda _e: canvas.unbind_all("<MouseWheel>"))

    def add_step_label(row: int, text: str) -> None:
        ttk.Label(steps, text=text, style="Step.TLabel").grid(
            row=row, column=0, columnspan=3, sticky="w", pady=(6, 2)
        )

    def normalize_paths() -> tuple[str, str]:
        policy = resolve_policy_path(policy_var.get())
        audit = abs_path(audit_var.get()) or default_audit_path()
        policy_var.set(policy)
        audit_var.set(audit)
        return policy, audit

    def browse_policy() -> None:
        initial = Path(policy_var.get() or default_policy_path())
        chosen = filedialog.askopenfilename(
            title="选择策略文件",
            filetypes=[("YAML", "*.yaml"), ("YAML", "*.yml"), ("全部", "*")],
            initialdir=str(initial.parent) if initial.parent.exists() else str(repo_root()),
        )
        if chosen:
            policy_var.set(abs_path(chosen) or chosen)

    def browse_audit() -> None:
        initial = Path(audit_var.get() or default_audit_path())
        chosen = filedialog.asksaveasfilename(
            title="选择审计日志",
            defaultextension=".jsonl",
            filetypes=[("JSONL", "*.jsonl"), ("全部", "*")],
            initialdir=str(initial.parent) if initial.parent.exists() else str(Path.cwd()),
            initialfile=initial.name or "audit.jsonl",
        )
        if chosen:
            audit_var.set(abs_path(chosen) or chosen)

    add_step_label(0, "1. 策略文件（绝对路径）")
    policy_entry = ttk.Entry(steps, textvariable=policy_var)
    policy_entry.grid(row=1, column=0, columnspan=2, sticky="ew")
    ttk.Button(steps, text="浏览", command=browse_policy).grid(row=1, column=2, padx=(8, 0))

    add_step_label(2, "2. 审计日志（绝对路径）")
    audit_entry = ttk.Entry(steps, textvariable=audit_var)
    audit_entry.grid(row=3, column=0, columnspan=2, sticky="ew")
    ttk.Button(steps, text="浏览", command=browse_audit).grid(row=3, column=2, padx=(8, 0))

    add_step_label(4, "3. 角色")
    role_box = ttk.Combobox(steps, textvariable=role_var, values=ROLES, state="readonly", width=20)
    role_box.grid(row=5, column=0, sticky="w")

    add_step_label(6, "4. 工具")
    tool_box = ttk.Combobox(steps, textvariable=tool_var, values=TOOLS, state="readonly", width=20)
    tool_box.grid(row=7, column=0, sticky="w")

    add_step_label(8, "5. 操作者名字")
    ttk.Entry(steps, textvariable=actor_var, width=28).grid(row=9, column=0, columnspan=2, sticky="w")

    add_step_label(10, "6. 点按钮：按当前策略检查是否允许")
    tk.Button(
        steps,
        text="检查是否允许",
        command=lambda: on_check(),
        font=("", 18, "bold"),
        padx=18,
        pady=8,
    ).grid(row=11, column=0, columnspan=2, sticky="w", pady=(2, 4))

    verdict_title = tk.Label(steps, text="尚未检查", font=("", 28, "bold"), fg="#4b5563", anchor="w")
    verdict_title.grid(row=12, column=0, columnspan=3, sticky="ew", pady=(4, 0))
    verdict_detail = tk.Label(steps, text="", font=("", 13), fg="#111827", anchor="w", justify="left", wraplength=780)
    verdict_detail.grid(row=13, column=0, columnspan=3, sticky="ew")

    add_step_label(14, "7. 会话 ID（默认已生成；双人批准必须用同一个）")
    ttk.Entry(steps, textvariable=session_var).grid(row=15, column=0, columnspan=2, sticky="ew")
    ttk.Button(steps, text="换一个", command=lambda: session_var.set(new_session_id())).grid(
        row=15, column=2, padx=(8, 0)
    )

    add_step_label(16, "8. 审批人1、审批人2（每次点批准登记一个人：先 1 后 2）")
    ttk.Label(steps, text="审批人1").grid(row=17, column=0, sticky="w")
    ttk.Entry(steps, textvariable=approver1_var, width=18).grid(row=17, column=1, sticky="w")
    ttk.Label(steps, text="审批人2").grid(row=18, column=0, sticky="w", pady=(4, 0))
    ttk.Entry(steps, textvariable=approver2_var, width=18).grid(row=18, column=1, sticky="w", pady=(4, 0))
    ttk.Button(steps, text="批准", style="Action.TButton", command=lambda: on_approve()).grid(
        row=17, column=2, rowspan=2, padx=(8, 0), sticky="ns"
    )
    ttk.Label(
        steps,
        text="同一人点两次不算两票。点批准后会按当前策略再检查一次。",
        style="Hint.TLabel",
    ).grid(row=19, column=0, columnspan=3, sticky="w", pady=(4, 0))

    add_step_label(20, "9. 把刚才的检查结果写入审计记录")
    ttk.Button(steps, text="写入审计记录", style="Action.TButton", command=lambda: on_record()).grid(
        row=21, column=0, sticky="w"
    )

    add_step_label(22, "10. 可选：跑官方 demo（输出写到下方日志）")
    ttk.Button(steps, text="跑官方 demo", command=lambda: on_demo()).grid(row=23, column=0, sticky="w")

    log_frame = ttk.LabelFrame(outer, text="最近审计 / 检查结果", padding=6)
    log_frame.grid(row=2, column=0, sticky="nsew")
    log_frame.columnconfigure(0, weight=1)
    log_frame.rowconfigure(0, weight=1)
    log = tk.Text(log_frame, height=10, wrap="word", state="disabled")
    scroll = ttk.Scrollbar(log_frame, command=log.yview)
    log.configure(yscrollcommand=scroll.set)
    log.grid(row=0, column=0, sticky="nsew")
    scroll.grid(row=0, column=1, sticky="ns")

    def set_log(text: str) -> None:
        log.configure(state="normal")
        log.delete("1.0", "end")
        log.insert("1.0", text)
        log.configure(state="disabled")

    def refresh_log(header: str) -> None:
        _, audit = normalize_paths()
        set_log(header.rstrip() + "\n\n—— 最近审计 ——\n" + recent_events_text(audit))

    def show_verdict(title: str, detail: str, kind: str) -> None:
        colors = {"allow": "#127a2c", "deny": "#b42318", "error": "#9a6700", "idle": "#4b5563"}
        verdict_title.config(text=title, fg=colors.get(kind, "#111827"))
        verdict_detail.config(text=detail)

    def apply_check_result(result: CheckResult) -> None:
        last_result["value"] = result
        kind = "allow" if result.allowed else "deny"
        title = "允许" if result.allowed else "拒绝"
        extra = []
        if result.approvals_needed:
            extra.append(f"还差 {result.approvals_needed} 个不同审批人")
        if result.approvers:
            extra.append("已有审批人：" + "、".join(result.approvers))
        detail = "原因：" + result.reason
        if extra:
            detail += "\n" + "\n".join(extra)
        show_verdict(title, detail, kind)
        refresh_log(format_verdict(result))

    def on_check() -> None:
        policy, audit = normalize_paths()
        session = session_var.get().strip() or None
        actor = actor_var.get().strip() or None
        try:
            result = perform_check(
                policy_path=policy,
                audit_path=audit,
                role=role_var.get().strip(),
                tool=tool_var.get().strip(),
                actor=actor,
                session=session,
            )
        except Exception as exc:  # noqa: BLE001 — surface load/IO errors in the panel
            last_result["value"] = None
            show_verdict("无法检查", str(exc), "error")
            refresh_log(f"无法检查：{exc}")
            return
        apply_check_result(result)

    def on_approve() -> None:
        _, audit = normalize_paths()
        session = session_var.get().strip()
        tool = tool_var.get().strip()
        if not session:
            messagebox.showinfo("agent-gate", "请填写会话 ID。")
            return
        existing = existing_approvers(audit, session, tool)
        name = pick_approver_to_submit(approver1_var.get(), approver2_var.get(), existing)
        if not name:
            messagebox.showinfo("agent-gate", "请填写审批人1 或 审批人2。")
            return
        try:
            outcome = perform_approve(
                audit_path=audit, session=session, tool=tool, approver=name
            )
        except Exception as exc:  # noqa: BLE001
            show_verdict("无法批准", str(exc), "error")
            refresh_log(f"无法批准：{exc}")
            return
        if outcome.duplicate:
            messagebox.showinfo("agent-gate", outcome.message)
        refresh_log(outcome.message)
        on_check()

    def on_record() -> None:
        _, audit = normalize_paths()
        result = last_result["value"]
        if result is None:
            messagebox.showinfo("agent-gate", "请先点「检查是否允许」。")
            return
        actor = (result.actor or actor_var.get() or "").strip()
        if not actor:
            messagebox.showinfo("agent-gate", "请填写操作者名字。")
            return
        session = (result.session or session_var.get() or "").strip()
        if not session:
            messagebox.showinfo("agent-gate", "请填写会话 ID。")
            return
        try:
            row = perform_record(
                audit_path=audit,
                session=session,
                actor=actor,
                tool=result.tool,
                decision=result.decision,
                role=result.role,
                reason=result.reason,
            )
        except Exception as exc:  # noqa: BLE001
            show_verdict("无法写入", str(exc), "error")
            refresh_log(f"无法写入审计：{exc}")
            return
        refresh_log("已写入审计记录：\n" + json.dumps(row, ensure_ascii=False))

    def on_demo() -> None:
        policy, audit = normalize_paths()
        try:
            code, output = capture_demo(policy, audit)
        except Exception as exc:  # noqa: BLE001
            refresh_log(f"demo 失败：{exc}")
            return
        header = f"demo 退出码 {code}\n{output.strip() or '(无输出)'}"
        refresh_log(header)

    def on_path_focus_out(_event: object | None = None) -> None:
        normalize_paths()

    policy_entry.bind("<FocusOut>", on_path_focus_out)
    audit_entry.bind("<FocusOut>", on_path_focus_out)

    normalize_paths()
    refresh_log(
        f"策略文件={policy_var.get()}\n审计日志={audit_var.get()}\n会话={session_var.get()}"
    )
    root.mainloop()
    return 0
