from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

from agent_gate.keys import PROVIDERS
from agent_gate.report import default_date_range, query_usage

STATIC_DIR = Path(__file__).resolve().parent / "static"


def page_html() -> str:
    return (STATIC_DIR / "index.html").read_text(encoding="utf-8")


def _parse_day(value: str | None) -> date | None:
    text = (value or "").strip()
    if not text:
        return None
    return datetime.strptime(text, "%Y-%m-%d").date()


def dispatch_api(path: str, body: dict[str, Any] | None = None) -> tuple[int, dict[str, Any]]:
    payload = body or {}
    try:
        if path == "/api/usage":
            start, end = default_date_range()
            from_date = _parse_day(str(payload.get("from") or "")) or start
            to_date = _parse_day(str(payload.get("to") or "")) or end
            raw_providers = payload.get("providers")
            if isinstance(raw_providers, list) and raw_providers:
                providers = tuple(str(item) for item in raw_providers if str(item).strip())
            else:
                providers = PROVIDERS
            report = query_usage(
                text=str(payload.get("keys") or ""),
                from_date=from_date,
                to_date=to_date,
                providers=providers,
            )
            return 200, report.as_dict()
        if path == "/api/defaults":
            start, end = default_date_range()
            return 200, {"ok": True, "from": start.isoformat(), "to": end.isoformat()}
        return 404, {"ok": False, "error": f"unknown path {path}"}
    except Exception as exc:  # noqa: BLE001 — return errors to the page, never echo keys
        return 400, {"ok": False, "error": str(exc)}


class GateHTTPServer:
    def __init__(self, server: Any) -> None:
        self.server = server

    @property
    def url(self) -> str:
        host, port = self.server.server_address[:2]
        return f"http://{host}:{port}/"

    @property
    def port(self) -> int:
        return int(self.server.server_address[1])

    def serve_forever(self) -> None:
        self.server.serve_forever()

    def shutdown(self) -> None:
        self.server.shutdown()
        self.server.server_close()


def make_server(host: str = "127.0.0.1", port: int = 8765) -> GateHTTPServer:
    from http.server import BaseHTTPRequestHandler, HTTPServer

    html = page_html()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args: Any) -> None:
            return

        def _send(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(body)
            self.close_connection = True

        def _read_json(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0:
                return {}
            raw = self.rfile.read(length)
            if not raw:
                return {}
            data = json.loads(raw.decode("utf-8"))
            if not isinstance(data, dict):
                raise ValueError("JSON body must be an object")
            return data

        def do_GET(self) -> None:  # noqa: N802
            route = self.path.split("?", 1)[0]
            if route in {"/", "/index.html"}:
                self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")
                return
            if route.startswith("/api/"):
                status, data = dispatch_api(route, {})
                blob = json.dumps(data, ensure_ascii=False).encode("utf-8")
                self._send(status, blob, "application/json; charset=utf-8")
                return
            self._send(404, b"not found", "text/plain; charset=utf-8")

        def do_POST(self) -> None:  # noqa: N802
            route = self.path.split("?", 1)[0]
            try:
                body = self._read_json()
            except (ValueError, json.JSONDecodeError) as exc:
                blob = json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False).encode(
                    "utf-8"
                )
                self._send(400, blob, "application/json; charset=utf-8")
                return
            status, data = dispatch_api(route, body)
            blob = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self._send(status, blob, "application/json; charset=utf-8")

    try:
        httpd = HTTPServer((host, port), Handler)
    except OSError:
        if port == 0:
            raise
        httpd = HTTPServer((host, 0), Handler)
    return GateHTTPServer(httpd)


def run_gui(host: str = "127.0.0.1", port: int = 8765, open_browser: bool = True) -> int:
    import threading
    import time
    import webbrowser

    server = make_server(host=host, port=port)
    url = server.url
    print(f"agent-gate gui  {url}", flush=True)
    if open_browser:
        def _open() -> None:
            time.sleep(0.25)
            webbrowser.open(url)

        threading.Thread(target=_open, daemon=True).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped", flush=True)
    finally:
        server.server.server_close()
    return 0
