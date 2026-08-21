from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from threading import Thread

from agent_gate.models import UsageReport, UsageRow


def test_page_is_plain_usage_tool() -> None:
    from agent_gate.gui import page_html

    html = page_html()
    assert "统计额度" in html
    assert "合计" in html
    assert "<textarea" in html
    assert "OpenRouter" in html
    assert "DeepSeek" in html
    assert "OpenAI" in html
    assert "能不能做" not in html
    assert "实习生" not in html
    assert "dual_control" not in html
    assert "智能统计" not in html
    assert "gradient" not in html.lower()
    assert "emoji" not in html.lower()
    assert "purple" not in html.lower()
    assert "#7c3aed" not in html.lower()
    assert "glow" not in html.lower()
    assert "\U0001f389" not in html
    assert "system-ui" in html or "sans-serif" in html


def test_dispatch_usage_never_echoes_secret(monkeypatch) -> None:
    from agent_gate import gui

    secret = "sk-or-v1-abcdefghijklmnopqrstuvwxyz"

    def fake_query(**kwargs):
        assert secret in kwargs["text"]
        return UsageReport(
            rows=[
                UsageRow(
                    masked="sk-or-...wxyz",
                    provider="openrouter",
                    used="1 USD",
                    remaining="2 USD",
                    cost="1 USD",
                    note="OpenRouter 只返回当前 UTC 月用量",
                )
            ],
            totals={"used": "1 USD", "remaining": "2 USD", "cost": "1 USD"},
            from_date=date(2026, 7, 1),
            to_date=date(2026, 8, 1),
        )

    monkeypatch.setattr(gui, "query_usage", fake_query)
    status, data = gui.dispatch_api(
        "/api/usage",
        {
            "keys": secret,
            "from": "2026-07-01",
            "to": "2026-08-01",
            "providers": ["openrouter"],
        },
    )
    blob = json.dumps(data)
    assert status == 200
    assert secret not in blob
    assert data["rows"][0]["masked"] == "sk-or-...wxyz"
    assert "合计" in data["totals_label"] or data["totals"]["used"] == "1 USD"


def test_http_server_serves_page_and_usage(tmp_path: Path, monkeypatch) -> None:
    from http.client import HTTPConnection

    from agent_gate import gui

    monkeypatch.setattr(
        gui,
        "query_usage",
        lambda **kwargs: UsageReport(
            rows=[
                UsageRow(
                    masked="sk-or-...wxyz",
                    provider="openrouter",
                    used="1 USD",
                    remaining="2 USD",
                    cost="1 USD",
                )
            ],
            totals={"used": "1 USD", "remaining": "2 USD", "cost": "1 USD"},
            from_date=date(2026, 7, 1),
            to_date=date(2026, 8, 1),
        ),
    )
    server = gui.make_server(host="127.0.0.1", port=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        conn = HTTPConnection("127.0.0.1", server.port, timeout=5)
        conn.request("GET", "/")
        res = conn.getresponse()
        body = res.read().decode("utf-8")
        assert res.status == 200
        assert "统计额度" in body
        assert "能不能做" not in body

        payload = json.dumps(
            {
                "keys": "openrouter:sk-or-v1-abcdefghijklmnopqrstuvwxyz",
                "from": "2026-07-01",
                "to": "2026-08-01",
            }
        ).encode("utf-8")
        conn.request("POST", "/api/usage", payload, {"Content-Type": "application/json"})
        checked = conn.getresponse()
        data = json.loads(checked.read().decode("utf-8"))
        assert checked.status == 200
        assert "abcdefghijklmnopqrstuvwxyz" not in json.dumps(data)
        assert data["rows"][0]["masked"].endswith("wxyz")
    finally:
        try:
            conn.close()
        except Exception:
            pass
        server.shutdown()
        thread.join(timeout=2)
