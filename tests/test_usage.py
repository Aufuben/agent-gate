from __future__ import annotations

import json
from datetime import date
from typing import Any

import pytest

from agent_gate.models import OPENAI_PERSONAL_KEY_MSG
from agent_gate.report import query_usage


OR_KEY = "sk-or-v1-abcdefghijklmnopqrstuvwxyz"
DS_KEY = "sk-deepseek1234567890abcdef"
OA_KEY = "sk-proj-abcdefghijklmnopqrstuvwxyz"
OA_ADMIN = "sk-admin-abcdefghijklmnopqrstuvwxyz"


class FakeHttp:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, str]]] = []
        self.by_url: dict[str, Any] = {}
        self.by_bearer: dict[str, Any] = {}
        self.fail_bearer: dict[str, BaseException] = {}

    def __call__(self, url: str, headers: dict[str, str], timeout: float = 15.0) -> Any:
        self.calls.append((url, dict(headers)))
        auth = headers.get("Authorization", "")
        token = auth.removeprefix("Bearer ").strip()
        if token in self.fail_bearer:
            raise self.fail_bearer[token]
        if token in self.by_bearer:
            return self.by_bearer[token]
        if url in self.by_url:
            return self.by_url[url]
        raise AssertionError(f"unexpected request {url}")


def test_openrouter_maps_monthly_usage_and_remaining() -> None:
    http = FakeHttp()
    http.by_bearer[OR_KEY] = {
        "data": {
            "label": "dev",
            "limit": 10,
            "limit_remaining": 8.5,
            "usage": 12.0,
            "usage_monthly": 1.5,
        }
    }
    report = query_usage(
        f"openrouter:{OR_KEY}",
        from_date=date(2026, 7, 1),
        to_date=date(2026, 8, 1),
        http_get=http,
    )
    assert len(report.rows) == 1
    row = report.rows[0]
    assert row.masked == "sk-or-...wxyz"
    assert row.provider == "openrouter"
    assert row.used == "1.5 USD"
    assert row.remaining == "8.5 USD"
    assert row.cost == "1.5 USD"
    assert OR_KEY not in json.dumps(row.as_dict())
    assert "自定义日期" in (row.note or "")
    assert http.calls[0][0] == "https://openrouter.ai/api/v1/key"


def test_deepseek_balance_not_monthly_usage() -> None:
    http = FakeHttp()
    http.by_bearer[DS_KEY] = {
        "is_available": True,
        "balance_infos": [
            {
                "currency": "CNY",
                "total_balance": "0.98",
                "granted_balance": "0.00",
                "topped_up_balance": "0.98",
            }
        ],
    }
    report = query_usage(
        f"deepseek:{DS_KEY}",
        from_date=date(2026, 7, 1),
        to_date=date(2026, 8, 1),
        http_get=http,
    )
    row = report.rows[0]
    assert row.provider == "deepseek"
    assert row.remaining == "0.98 CNY"
    assert row.used is None
    assert row.cost is None
    assert "月度" in (row.note or "")
    assert http.calls[0][0] == "https://api.deepseek.com/user/balance"


def test_openai_user_key_does_not_invent_spend() -> None:
    from agent_gate.fetch import HttpError

    http = FakeHttp()
    http.fail_bearer[OA_KEY] = HttpError(401, "Unauthorized")
    report = query_usage(
        f"openai:{OA_KEY}",
        from_date=date(2026, 7, 1),
        to_date=date(2026, 8, 1),
        http_get=http,
    )
    row = report.rows[0]
    assert row.error == OPENAI_PERSONAL_KEY_MSG
    assert row.used is None
    assert row.cost is None
    assert row.remaining is None
    assert OA_KEY not in (row.error or "")


def test_openai_admin_key_sums_costs() -> None:
    http = FakeHttp()
    http.by_bearer[OA_ADMIN] = {
        "data": [
            {
                "results": [
                    {"amount": {"currency": "usd", "value": 1.25}},
                    {"amount": {"currency": "usd", "value": 0.75}},
                ]
            }
        ]
    }
    report = query_usage(
        f"openai:{OA_ADMIN}",
        from_date=date(2026, 7, 1),
        to_date=date(2026, 8, 1),
        http_get=http,
    )
    row = report.rows[0]
    assert row.error is None
    assert row.cost == "2 USD"
    assert "organization/costs" in http.calls[0][0]


def test_one_failure_does_not_abort_others() -> None:
    http = FakeHttp()
    http.fail_bearer[OR_KEY] = TimeoutError("timed out")
    http.by_bearer[DS_KEY] = {
        "is_available": True,
        "balance_infos": [{"currency": "USD", "total_balance": "3.00"}],
    }
    report = query_usage(
        f"openrouter:{OR_KEY}\ndeepseek:{DS_KEY}",
        from_date=date(2026, 7, 1),
        to_date=date(2026, 8, 1),
        http_get=http,
    )
    assert len(report.rows) == 2
    by_prov = {r.provider: r for r in report.rows}
    assert by_prov["openrouter"].error
    assert "timed out" in by_prov["openrouter"].error.lower() or "timeout" in by_prov["openrouter"].error.lower() or "Timed" in by_prov["openrouter"].error
    assert by_prov["deepseek"].remaining == "3 USD"
    assert OR_KEY not in by_prov["openrouter"].error


def test_totals_sum_same_unit_only() -> None:
    http = FakeHttp()
    http.by_bearer[OR_KEY] = {
        "data": {"limit": 10, "limit_remaining": 4, "usage_monthly": 6, "usage": 6}
    }
    http.by_bearer[DS_KEY] = {
        "is_available": True,
        "balance_infos": [{"currency": "CNY", "total_balance": "9"}],
    }
    report = query_usage(
        f"openrouter:{OR_KEY}\ndeepseek:{DS_KEY}",
        from_date=date(2026, 7, 1),
        to_date=date(2026, 8, 1),
        http_get=http,
    )
    assert "6 USD" in report.totals["used"]
    assert "4 USD" in report.totals["remaining"]
    assert "9 CNY" in report.totals["remaining"]
    assert "6 USD" in report.totals["cost"]


def test_http_error_redacts_secrets() -> None:
    from agent_gate.fetch import redact

    leaked = f"Authorization: Bearer {OR_KEY}"
    assert OR_KEY not in redact(leaked)
    assert "..." in redact(leaked)
