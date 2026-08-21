from __future__ import annotations

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from typing import Any, Callable, Iterable, Sequence

from agent_gate.fetch import HttpError, get_json, redact
from agent_gate.keys import PROVIDERS, ParsedKey, mask_key, parse_keys
from agent_gate.models import OPENAI_PERSONAL_KEY_MSG, UsageReport, UsageRow, format_amount
from agent_gate.providers import HANDLERS

HttpGet = Callable[..., Any]


def default_date_range(today: date | None = None) -> tuple[date, date]:
    end = today or date.today()
    return end - timedelta(days=30), end


def _sum_field(rows: list[UsageRow], value_attr: str, unit_attr: str) -> str:
    buckets: dict[str, float] = defaultdict(float)
    found = False
    for row in rows:
        value = getattr(row, value_attr)
        unit = getattr(row, unit_attr)
        if value is None or not unit:
            continue
        buckets[str(unit)] += float(value)
        found = True
    if not found:
        return "—"
    parts = [format_amount(amount, unit) for unit, amount in buckets.items()]
    return "；".join(part for part in parts if part)


def _query_one(
    parsed: ParsedKey,
    from_date: date,
    to_date: date,
    http_get: HttpGet,
    timeout: float,
) -> UsageRow:
    if parsed.error:
        return UsageRow(
            masked=parsed.masked or mask_key(parsed.secret),
            provider=parsed.provider or "?",
            error=parsed.error,
        )
    handler = HANDLERS.get(parsed.provider)
    if handler is None:
        return UsageRow(
            masked=parsed.masked,
            provider=parsed.provider,
            error=f"未知平台 {parsed.provider}",
        )
    try:
        return handler(parsed, from_date, to_date, http_get=http_get, timeout=timeout)
    except HttpError as exc:
        if parsed.provider == "openai" and exc.status in {401, 403}:
            message = OPENAI_PERSONAL_KEY_MSG
        else:
            message = f"HTTP {exc.status}"
        return UsageRow(masked=parsed.masked, provider=parsed.provider, error=message)
    except Exception as exc:  # noqa: BLE001 — isolate per key
        text = redact(str(exc) or type(exc).__name__)
        return UsageRow(masked=parsed.masked, provider=parsed.provider, error=text)


def query_usage(
    text: str,
    from_date: date | None = None,
    to_date: date | None = None,
    providers: Sequence[str] | Iterable[str] | None = None,
    http_get: HttpGet | None = None,
    timeout: float = 15.0,
) -> UsageReport:
    start, end = default_date_range()
    start = from_date or start
    end = to_date or end
    selected = tuple(providers) if providers is not None else PROVIDERS
    parsed_rows = parse_keys(text, providers=selected)
    getter = http_get or get_json
    rows: list[UsageRow]
    if not parsed_rows:
        rows = []
    elif len(parsed_rows) == 1:
        rows = [_query_one(parsed_rows[0], start, end, getter, timeout)]
    else:
        workers = min(8, len(parsed_rows))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [
                pool.submit(_query_one, parsed, start, end, getter, timeout)
                for parsed in parsed_rows
            ]
            rows = [future.result() for future in futures]
    totals = {
        "used": _sum_field(rows, "used_value", "used_unit"),
        "remaining": _sum_field(rows, "remaining_value", "remaining_unit"),
        "cost": _sum_field(rows, "cost_value", "cost_unit"),
    }
    return UsageReport(rows=rows, totals=totals, from_date=start, to_date=end)


def format_table(report: UsageReport) -> str:
    lines = ["密钥\t平台\t已用\t剩余\t费用\t说明"]
    for row in report.rows:
        note = row.error or row.note or ""
        lines.append(
            "\t".join(
                [
                    row.masked,
                    row.provider,
                    row.used or "—",
                    row.remaining or "—",
                    row.cost or "—",
                    note,
                ]
            )
        )
    lines.append(
        "\t".join(
            [
                "合计",
                "",
                report.totals.get("used") or "—",
                report.totals.get("remaining") or "—",
                report.totals.get("cost") or "—",
                "",
            ]
        )
    )
    return "\n".join(lines)
