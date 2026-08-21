# agent-gate

内部 Agent 的工具调用控制面。Agent 必须先 `check` 再执行；决策写入审计日志；标了 `dual_control` 的写操作/破坏性工具在凑齐两个不同审批人 id 之前一律拒绝。

## 做什么

- 拦截工具调用：按 YAML policy 的角色 allow/deny 决定放行或拒绝
- 审计：JSONL（默认 `./audit.jsonl`），可导出 CSV 做月度权限/工具回顾
- 双人复核：同一 `session` + `tool` 需要两个不同的 `approver` id；同一人点两次不算

## Policy

提交的示例：`policies/example.yaml`。

- 角色：`intern` / `engineer` / `sre`
- `read_file`：所有角色允许
- `http_fetch`：仅 `engineer`、`sre`
- `shell`：拒绝 `intern`（其余已声明角色允许）
- `prod_restart`：仅 `sre`，且必须 `dual_control`
- `budget.max_calls_per_session` 可选；按该 session 已 `record` 的决策条数计数。未传 `--session` 时不套预算

未知角色、未知工具：拒绝。`deny` 优先于 `allow`。未配置 `allow` 且未配置 `deny` 的工具：拒绝。

## 安装

需要 Python 3.11+。

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## 库

```python
from agent_gate import Gate

gate = Gate(policy_path="policies/example.yaml", audit_path="audit.jsonl")
result = gate.check(role="intern", tool="read_file", actor="a")
if result.allowed:
    gate.record(session="S", actor="a", tool="read_file", args={}, decision="allow", role="intern")
else:
    gate.record(session="S", actor="a", tool="read_file", args={}, decision="deny", role="intern", reason=result.reason)
```

破坏性工具：先 `approve` 两次（不同 id），再 `check`。

## CLI / Demo

在仓库根目录：

```bash
agent-gate check --policy policies/example.yaml --role intern --tool prod_restart
# 退出码 1，拒绝

agent-gate check --policy policies/example.yaml --role intern --tool read_file
# 退出码 0，放行

agent-gate record --session S --actor a --tool read_file --args '{}' --decision allow
agent-gate approve --session S --tool prod_restart --approver alice
agent-gate approve --session S --tool prod_restart --approver bob
agent-gate check --policy policies/example.yaml --role sre --tool prod_restart --session S --actor sre-1
# 两名不同审批人之后退出码 0

agent-gate export-audit --from 2026-01-01 --out audit.csv
agent-gate demo
agent-gate gui
```

`--audit` 默认 `./audit.jsonl`。`check`：放行退出 0，拒绝退出 1。

## 图形界面

```bash
agent-gate gui
```

`agent-gate gui` 在 `127.0.0.1` 起一个本地页（默认端口 8765，占用则换随机端口）并打开浏览器：按策略检查、双人批准、写审计。点「浏览」会打开系统文件框（需要 tkinter），因为浏览器选文件得不到真实路径。

### Demo 退出码

| 码 | 含义 |
| --- | --- |
| 0 | 预期路径全部命中：`read_file` 放行；`prod_restart` 在两名不同审批人之前拒绝（含同一审批人点两次），补齐后放行 |
| 1 | 某步决策与预期不符 |
| 2 | policy 无法加载或路径不存在 |

```bash
pytest
```

## 许可证

MIT
