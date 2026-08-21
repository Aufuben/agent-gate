from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any

from agent_gate.keys import mask_key

_SECRET = re.compile(r"sk-[A-Za-z0-9_-]{8,}")


class HttpError(Exception):
    def __init__(self, status: int, body: str = "") -> None:
        self.status = int(status)
        self.body = body
        super().__init__(f"HTTP {self.status}")


def redact(text: str) -> str:
    def _replace(match: re.Match[str]) -> str:
        return mask_key(match.group(0))

    return _SECRET.sub(_replace, text or "")


def get_json(
    url: str,
    headers: dict[str, str] | None = None,
    timeout: float = 15.0,
) -> Any:
    req_headers = {
        "Accept": "application/json",
        "User-Agent": "agent-gate/0.2",
    }
    if headers:
        req_headers.update(headers)
    request = urllib.request.Request(url, headers=req_headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            body = ""
        raise HttpError(int(exc.code), redact(body)) from None
    except urllib.error.URLError as exc:
        reason = redact(str(getattr(exc, "reason", exc) or exc))
        raise TimeoutError(reason) from None
    except TimeoutError as exc:
        raise TimeoutError(redact(str(exc) or "timed out")) from None
    if not raw.strip():
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(redact(f"invalid JSON: {exc}")) from None
