from __future__ import annotations

from datetime import date
from typing import Any, Callable

from agent_gate.keys import ParsedKey
from agent_gate.models import UsageRow, format_amount

HttpGet = Callable[..., Any]

NOTE = "账户余额，非本月消耗"
URL = "https://api.deepseek.com/user/balance"


def query_deepseek(
    key: ParsedKey,
    from_date: date,
    to_date: date,
    http_get: HttpGet,
    timeout: float = 15.0,
) -> UsageRow:
    payload = http_get(URL, {"Authorization": f"Bearer {key.secret}"}, timeout=timeout)
    if not isinstance(payload, dict):
        return UsageRow(
            masked=key.masked,
            provider="deepseek",
            error="DeepSeek 返回无法解析",
            note=NOTE,
        )
    infos = payload.get("balance_infos") or []
    parts: list[str] = []
    values: list[tuple[float, str]] = []
    if isinstance(infos, list):
        for info in infos:
            if not isinstance(info, dict):
                continue
            currency = str(info.get("currency") or "").upper()
            total = info.get("total_balance")
            rendered = format_amount(total, currency)
            if rendered:
                parts.append(rendered)
            try:
                values.append((float(total), currency or "USD"))
            except (TypeError, ValueError):
                continue
    remaining = "；".join(parts) if parts else None
    remaining_value: float | None = None
    remaining_unit: str | None = None
    if len(values) == 1:
        remaining_value, remaining_unit = values[0]
    return UsageRow(
        masked=key.masked,
        provider="deepseek",
        used=None,
        remaining=remaining,
        cost=None,
        note=NOTE,
        remaining_value=remaining_value,
        remaining_unit=remaining_unit,
    )
