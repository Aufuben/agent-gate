from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable

from agent_gate.fetch import HttpError
from agent_gate.keys import ParsedKey
from agent_gate.models import OPENAI_PERSONAL_KEY_MSG, UsageRow, format_amount

HttpGet = Callable[..., Any]

URL = "https://api.openai.com/v1/organization/costs"


def query_openai(
    key: ParsedKey,
    from_date: date,
    to_date: date,
    http_get: HttpGet,
    timeout: float = 15.0,
) -> UsageRow:
    start = int(datetime(from_date.year, from_date.month, from_date.day, tzinfo=timezone.utc).timestamp())
    end = int(
        datetime(to_date.year, to_date.month, to_date.day, tzinfo=timezone.utc).timestamp()
        + timedelta(days=1).total_seconds()
    )
    url = f"{URL}?start_time={start}&end_time={end}&limit=180"
    try:
        payload = http_get(url, {"Authorization": f"Bearer {key.secret}"}, timeout=timeout)
    except HttpError as exc:
        if exc.status in {401, 403}:
            return UsageRow(
                masked=key.masked,
                provider="openai",
                error=OPENAI_PERSONAL_KEY_MSG,
            )
        return UsageRow(
            masked=key.masked,
            provider="openai",
            error=f"HTTP {exc.status}",
        )
    if not isinstance(payload, dict):
        return UsageRow(
            masked=key.masked,
            provider="openai",
            error="OpenAI 返回无法解析",
        )
    total = 0.0
    unit = "USD"
    found = False
    for bucket in payload.get("data") or []:
        if not isinstance(bucket, dict):
            continue
        for result in bucket.get("results") or []:
            if not isinstance(result, dict):
                continue
            amount = result.get("amount") or {}
            if not isinstance(amount, dict) or "value" not in amount:
                continue
            try:
                total += float(amount["value"])
            except (TypeError, ValueError):
                continue
            if amount.get("currency"):
                unit = str(amount["currency"]).upper()
            found = True
    if not found:
        return UsageRow(
            masked=key.masked,
            provider="openai",
            cost=format_amount(0, "USD"),
            cost_value=0.0,
            cost_unit="USD",
        )
    return UsageRow(
        masked=key.masked,
        provider="openai",
        cost=format_amount(total, unit),
        cost_value=total,
        cost_unit=unit,
    )
