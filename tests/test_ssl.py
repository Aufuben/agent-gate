from __future__ import annotations

import json
import ssl
import urllib.error
from datetime import date
from pathlib import Path
from typing import Any

from agent_gate.models import UsageReport, UsageRow


OR_KEY = "sk-or-v1-abcdefghijklmnopqrstuvwxyz"


def test_get_json_ssl_failure_shows_chinese_hint(monkeypatch) -> None:
    import urllib.request

    from agent_gate.fetch import SslVerifyError, get_json

    def boom(*args, **kwargs):
        raise urllib.error.URLError(
            ssl.SSLCertVerificationError(
                "certificate verify failed: self-signed certificate in certificate chain"
            )
        )

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    try:
        get_json("https://openrouter.ai/api/v1/key")
    except SslVerifyError as exc:
        text = str(exc)
    else:
        raise AssertionError("expected SslVerifyError")
    assert "跳过证书校验" in text
    assert "AGENT_GATE_INSECURE_SSL" in text or "环境变量" in text
    assert "_ssl.c" not in text
    assert "Traceback" not in text
    assert "CERTIFICATE_VERIFY_FAILED" not in text


def test_get_json_insecure_skips_verify(monkeypatch) -> None:
    import urllib.request

    from agent_gate.fetch import get_json

    captured: dict[str, Any] = {}

    class FakeResp:
        def read(self) -> bytes:
            return b'{"ok": true}'

        def __enter__(self) -> FakeResp:
            return self

        def __exit__(self, *args: object) -> None:
            return None

    def fake_urlopen(req, timeout=15.0, context=None):
        captured["context"] = context
        return FakeResp()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    payload = get_json("https://openrouter.ai/api/v1/key", insecure=True)
    assert payload == {"ok": True}
    ctx = captured["context"]
    assert ctx is not None
    assert ctx.verify_mode == ssl.CERT_NONE
    assert ctx.check_hostname is False


def test_get_json_default_uses_certifi(monkeypatch) -> None:
    import ssl as ssl_mod
    import urllib.request

    import certifi

    from agent_gate.fetch import get_json

    captured: dict[str, Any] = {}
    real_create = ssl_mod.create_default_context

    class FakeResp:
        def read(self) -> bytes:
            return b"{}"

        def __enter__(self) -> FakeResp:
            return self

        def __exit__(self, *args: object) -> None:
            return None

    def fake_create(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return real_create(*args, **kwargs)

    def fake_urlopen(req, timeout=15.0, context=None):
        captured["context"] = context
        return FakeResp()

    monkeypatch.setattr(ssl_mod, "create_default_context", fake_create)
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    get_json("https://openrouter.ai/api/v1/key")
    ctx = captured["context"]
    assert ctx is not None
    assert ctx.verify_mode == ssl.CERT_REQUIRED
    assert captured["kwargs"].get("cafile") == certifi.where()


def test_query_usage_passes_insecure_to_get_json(monkeypatch) -> None:
    from agent_gate import report

    seen: dict[str, Any] = {}

    def fake_get_json(url, headers=None, timeout=15.0, insecure=False):
        seen["insecure"] = insecure
        seen["url"] = url
        return {
            "data": {
                "limit": 10,
                "limit_remaining": 8,
                "usage_monthly": 2,
            }
        }

    monkeypatch.setattr(report, "get_json", fake_get_json)
    report.query_usage(
        f"openrouter:{OR_KEY}",
        from_date=date(2026, 7, 1),
        to_date=date(2026, 8, 1),
        insecure=True,
    )
    assert seen["insecure"] is True
    assert seen["url"] == "https://openrouter.ai/api/v1/key"


def test_query_usage_env_enables_insecure(monkeypatch) -> None:
    from agent_gate import report

    seen: dict[str, Any] = {}

    def fake_get_json(url, headers=None, timeout=15.0, insecure=False):
        seen["insecure"] = insecure
        return {
            "data": {"limit": 10, "limit_remaining": 8, "usage_monthly": 2}
        }

    monkeypatch.setattr(report, "get_json", fake_get_json)
    monkeypatch.setenv("AGENT_GATE_INSECURE_SSL", "1")
    report.query_usage(
        f"openrouter:{OR_KEY}",
        from_date=date(2026, 7, 1),
        to_date=date(2026, 8, 1),
    )
    assert seen["insecure"] is True


def test_usage_cli_passes_insecure(tmp_path: Path, monkeypatch) -> None:
    from agent_gate import cli

    keys = tmp_path / "keys.txt"
    keys.write_text(f"openrouter:{OR_KEY}\n", encoding="utf-8")
    captured: dict[str, Any] = {}

    def fake_query(**kwargs):
        captured.update(kwargs)
        return UsageReport(
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
        )

    monkeypatch.setattr(cli, "query_usage", fake_query)
    code = cli.main(["usage", "--keys-file", str(keys), "--insecure"])
    assert code == 0
    assert captured.get("insecure") is True


def test_dispatch_passes_insecure(monkeypatch) -> None:
    from agent_gate import gui

    captured: dict[str, Any] = {}

    def fake_query(**kwargs):
        captured.update(kwargs)
        return UsageReport(
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
        )

    monkeypatch.setattr(gui, "query_usage", fake_query)
    status, data = gui.dispatch_api(
        "/api/usage",
        {
            "keys": f"openrouter:{OR_KEY}",
            "insecure": True,
            "providers": ["openrouter"],
        },
    )
    assert status == 200
    assert captured.get("insecure") is True
    assert OR_KEY not in json.dumps(data)


def test_page_has_insecure_checkbox() -> None:
    from agent_gate.gui import page_html

    html = page_html()
    assert "跳过证书校验" in html
    assert "id=\"insecure\"" in html or "id='insecure'" in html
    assert "insecure:" in html
