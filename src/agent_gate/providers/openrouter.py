from __future__ import annotations

from datetime import date
from typing import Any, Callable

from agent_gate.keys import ParsedKey
from agent_gate.models import UsageRow, format_amount

HttpGet = Callable[..., Any]

NOTE = "OpenRouter 只返回当前 UTC 月用量与该 Key 额度，不能按自定义日期区间查询"
URL = "https://openrouter.ai/api/v1/key"


def query_openrouter(
    key: ParsedKey,
    from_date: date,
    to_date: date,
    http_get: HttpGet,
    timeout: float = 15.0,
) -> UsageRow:
    payload = http_get(URL, {"Authorization": f"Bearer {key.secret}"}, timeout=timeout)
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        return UsageRow(
            masked=key.masked,
            provider="openrouter",
            error="OpenRouter 返回无法解析",
            note=NOTE,
        )
    monthly = data.get("usage_monthly")
    remaining_raw = data.get("limit_remaining")
    limit_raw = data.get("limit")
    used_value: float | None = None
    if monthly is not None:
        used_value = float(monthly)
    remaining_value: float | None = None
    remaining: str | None
    remaining_unit: str | None = None
    if remaining_raw is None and limit_raw is None:
        remaining = "不限"
    elif remaining_raw is None:
        remaining = None
    else:
        remaining_value = float(remaining_raw)
        remaining_unit = "USD"
        remaining = format_amount(remaining_value, "USD")
    used = format_amount(used_value, "USD") if used_value is not None else None
    return UsageRow(
        masked=key.masked,
        provider="openrouter",
        used=used,
        remaining=remaining,
        cost=used,
        note=NOTE,
        used_value=used_value,
        used_unit="USD" if used_value is not None else None,
        remaining_value=remaining_value,
        remaining_unit=remaining_unit,
        cost_value=used_value,
        cost_unit="USD" if used_value is not None else None,
    )
