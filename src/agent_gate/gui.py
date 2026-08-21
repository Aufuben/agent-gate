from __future__ import annotations

import json
from pathlib import Path


def abs_path(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        return ""
    return str(Path(text).expanduser().resolve())


def run_gui(policy_path: str = "policies/example.yaml", audit_path: str = "audit.jsonl") -> int:
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox, ttk
    except ImportError as exc:
        print(f"gui unavailable: tkinter is not installed ({exc})", flush=True)
        return 2

    from agent_gate.audit import AuditLog

    try:
        root = tk.Tk()
    except tk.TclError as exc:
        print(f"gui unavailable: {exc}", flush=True)
        return 2
    root.title("agent-gate")
    root.minsize(640, 420)

    policy_var = tk.StringVar(value=abs_path(policy_path) or policy_path)
    audit_var = tk.StringVar(value=abs_path(audit_path) or audit_path)

    frm = ttk.Frame(root, padding=12)
    frm.pack(fill="both", expand=True)

    ttk.Label(frm, text="输入 = policy 路径").grid(row=0, column=0, sticky="w")
    policy_entry = ttk.Entry(frm, textvariable=policy_var, width=72)
    policy_entry.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 8))
    ttk.Button(
        frm,
        text="选择 policy",
        command=lambda: _pick_file(
            policy_var,
            filetypes=[("YAML", "*.yaml"), ("YAML", "*.yml"), ("All", "*")],
        ),
    ).grid(row=1, column=2, padx=(8, 0))

    ttk.Label(frm, text="输出 = audit 日志路径").grid(row=2, column=0, sticky="w")
    audit_entry = ttk.Entry(frm, textvariable=audit_var, width=72)
    audit_entry.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(0, 8))
    ttk.Button(
        frm,
        text="选择 audit",
        command=lambda: _pick_file(audit_var, filetypes=[("JSONL", "*.jsonl"), ("All", "*")]),
    ).grid(row=3, column=2, padx=(8, 0))

    text = tk.Text(frm, height=18, wrap="none")
    text.grid(row=5, column=0, columnspan=3, sticky="nsew", pady=(8, 0))
    frm.columnconfigure(0, weight=1)
    frm.rowconfigure(5, weight=1)

    def refresh() -> None:
        policy_resolved = abs_path(policy_var.get())
        audit_resolved = abs_path(audit_var.get())
        if policy_resolved:
            policy_var.set(policy_resolved)
        if audit_resolved:
            audit_var.set(audit_resolved)
        path = Path(audit_var.get())
        text.delete("1.0", "end")
        header = (
            f"policy={policy_var.get()}\n"
            f"audit={path}\n"
            "last decisions:\n"
        )
        text.insert("1.0", header)
        if not path.is_file():
            text.insert("end", "(文件不存在)\n")
            return
        rows = AuditLog(path).last_decisions(limit=30)
        if not rows:
            text.insert("end", "(无 decision 记录)\n")
            return
        for row in reversed(rows):
            line = json.dumps(row, ensure_ascii=False)
            text.insert("end", line + "\n")

    ttk.Button(frm, text="刷新 last decisions", command=refresh).grid(
        row=4, column=0, sticky="w"
    )

    def _pick_file(var: tk.StringVar, filetypes: list) -> None:
        chosen = filedialog.askopenfilename(filetypes=filetypes)
        if chosen:
            var.set(abs_path(chosen) or chosen)
            refresh()

    def on_policy_missing() -> None:
        p = Path(policy_var.get())
        if not p.is_file():
            messagebox.showwarning("agent-gate", f"policy 不存在: {p}")

    ttk.Button(frm, text="检查 policy 是否存在", command=on_policy_missing).grid(
        row=4, column=1, sticky="w"
    )

    refresh()
    root.mainloop()
    return 0
