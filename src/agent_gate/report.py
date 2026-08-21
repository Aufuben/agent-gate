from __future__ import annotations

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from functools import partial
from typing import Any, Callable, Iterable, Sequence

from agent_gate.fetch import (
    HttpError,
    SslVerifyError,
    SSL_VERIFY_HINT,
    get_json,
    is_cert_verify_error,
    redact,
    resolve_insecure_ssl,
)
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
    except SslVerifyError as exc:
        return UsageRow(masked=parsed.masked, provider=parsed.provider, error=str(exc))
    except Exception as exc:  # noqa: BLE001 — isolate per key
        if is_cert_verify_error(exc):
            text = SSL_VERIFY_HINT
        else:
            text = redact(str(exc) or type(exc).__name__)
        return UsageRow(masked=parsed.masked, provider=parsed.provider, error=text)


def query_usage(
    text: str,
    from_date: date | None = None,
    to_date: date | None = None,
    providers: Sequence[str] | Iterable[str] | None = None,
    http_get: HttpGet | None = None,
    timeout: float = 15.0,
    insecure: bool | None = None,
) -> UsageReport:
    start, end = default_date_range()
    start = from_date or start
    end = to_date or end
    selected = tuple(providers) if providers is not None else PROVIDERS
    parsed_rows = parse_keys(text, providers=selected)
    getter = http_get or partial(get_json, insecure=resolve_insecure_ssl(insecure))
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
    totals, totals_note, subtotals = _build_totals(rows)
    return UsageReport(
        rows=rows,
        totals=totals,
        from_date=start,
        to_date=end,
        totals_note=totals_note,
        subtotals=subtotals,
    )


def _provider_order(rows: list[UsageRow]) -> list[str]:
    seen: list[str] = []
    for row in rows:
        if row.provider not in seen:
            seen.append(row.provider)
    return seen


def _amount_kinds_and_units(rows: list[UsageRow]) -> tuple[set[str], set[str]]:
    kinds: set[str] = set()
    units: set[str] = set()
    for row in rows:
        if row.error:
            continue
        if row.provider == "deepseek":
            if row.remaining_value is not None and row.remaining_unit:
                kinds.add("balance")
                units.add(row.remaining_unit)
            elif row.remaining:
                kinds.add("balance")
                if "；" in row.remaining:
                    kinds.add("balance-multi")
            continue
        if row.used_value is not None and row.used_unit:
            kinds.add("usage")
            units.add(row.used_unit)
        if row.remaining_value is not None and row.remaining_unit:
            kinds.add("usage")
            units.add(row.remaining_unit)
        elif row.remaining:
            kinds.add("usage")
    return kinds, units


def _amount_is_mixed(rows: list[UsageRow]) -> bool:
    kinds, units = _amount_kinds_and_units(rows)
    if "balance-multi" in kinds:
        return True
    if "balance" in kinds and "usage" in kinds:
        return True
    return len(units) > 1


def _amount_text_for_rows(rows: list[UsageRow]) -> str:
    usable = [row for row in rows if not row.error]
    if not usable:
        return "—"
    providers = {row.provider for row in usable if row.display_amount()}
    if providers <= {"deepseek"}:
        summed = _sum_field(usable, "remaining_value", "remaining_unit")
        if summed != "—":
            return summed
        parts = [row.remaining for row in usable if row.remaining]
        return "；".join(parts) if parts else "—"
    used = _sum_field(usable, "used_value", "used_unit")
    remaining = _sum_field(usable, "remaining_value", "remaining_unit")
    parts: list[str] = []
    if used != "—":
        parts.append(f"已用 {used}")
    unlimited = any(row.remaining == "不限" for row in usable)
    if remaining != "—":
        parts.append(f"剩余 {remaining}")
    elif unlimited:
        parts.append("剩余 不限")
    return "；".join(parts) if parts else "—"


def _build_totals(rows: list[UsageRow]) -> tuple[dict[str, str], str, list[dict[str, str]]]:
    cost = _sum_field(rows, "cost_value", "cost_unit")
    if not rows:
        return {"amount": "—", "cost": "—"}, "", []
    if _amount_is_mixed(rows):
        subtotals = [
            {
                "provider": provider,
                "amount": _amount_text_for_rows([row for row in rows if row.provider == provider]),
                "cost": _sum_field(
                    [row for row in rows if row.provider == provider],
                    "cost_value",
                    "cost_unit",
                ),
                "label": f"小计 {provider}",
            }
            for provider in _provider_order(rows)
        ]
        return {"amount": "—", "cost": cost}, "币种或口径不同，未合并合计", subtotals
    return {"amount": _amount_text_for_rows(rows), "cost": cost}, "", []


def format_table(report: UsageReport) -> str:
    lines = ["平台\t密钥\t余额或用量\t费用\t说明"]
    for row in report.rows:
        note = row.error or row.note or ""
        lines.append(
            "\t".join(
                [
                    row.provider,
                    row.masked,
                    row.display_amount() or "—",
                    row.cost or "—",
                    note,
                ]
            )
        )
    for item in report.subtotals:
        lines.append(
            "\t".join(
                [
                    item.get("label") or f"小计 {item.get('provider') or ''}",
                    "",
                    item.get("amount") or "—",
                    item.get("cost") or "—",
                    "",
                ]
            )
        )
    lines.append(
        "\t".join(
            [
                "合计",
                "",
                report.totals.get("amount") or "—",
                report.totals.get("cost") or "—",
                report.totals_note or "",
            ]
        )
    )
    return "\n".join(lines)
