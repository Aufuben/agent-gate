# agent-gate

把多把 API Key 贴进来，查询每把的额度/用量，并给出合计。不保存 Key。

支持 **OpenRouter**、**DeepSeek**、**OpenAI**（尽力而为）。某平台没法按 Key 查月度账单时，表格会写明原因，不会编造数字。

## 网页

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
agent-gate gui
```

浏览器打开本地页（默认 `http://127.0.0.1:8765/`）。

1. 把 Key 粘到文本框，一行一把。可写成 `openrouter:sk-or-...`、`deepseek:sk-...`、`openai:sk-...`；`sk-or-` 会自动识别为 OpenRouter。
2. 日期默认最近 30 天。
3. 勾选平台，点 **统计额度**。
4. 表格只显示掩码（`sk-...abcd`）。底下一行是 **合计**。

提交后页面不再显示完整 Key。

## 命令行

```bash
agent-gate usage --keys-file keys.txt --from 2026-07-01 --to 2026-08-01
```

`keys.txt` 已加入 `.gitignore`。格式见 `keys.example.txt`。

## 各平台能查到什么

- **OpenRouter**：`GET https://openrouter.ai/api/v1/key`。返回该 Key 当前 UTC 月用量和额度，不能按自定义日期区间查。
- **DeepSeek**：`GET https://api.deepseek.com/user/balance`。只有当前余额，没有按 Key 的月度用量。
- **OpenAI**：普通个人 `sk-` 无法按把查询月度账单，需要组织 Admin Key。若 Admin Key 可用，会请求官方 `GET /v1/organization/costs`。

一把 Key 失败不影响其他 Key。日志里的密钥会做掩码。

```bash
pytest
```

## 许可证

MIT
