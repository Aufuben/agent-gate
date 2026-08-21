from __future__ import annotations

import json
import os
import re
import ssl
import urllib.error
import urllib.request
from typing import Any

import certifi

from agent_gate.keys import mask_key

_SECRET = re.compile(r"sk-[A-Za-z0-9_-]{8,}")

INSECURE_SSL_ENV = "AGENT_GATE_INSECURE_SSL"
SSL_VERIFY_HINT = "公司代理/自签名证书时勾选「跳过证书校验」或设环境变量。"


class HttpError(Exception):
    def __init__(self, status: int, body: str = "") -> None:
        self.status = int(status)
        self.body = body
        super().__init__(f"HTTP {self.status}")


class SslVerifyError(Exception):
    def __init__(self, detail: str = "") -> None:
        self.detail = detail
        super().__init__(SSL_VERIFY_HINT)


def redact(text: str) -> str:
    def _replace(match: re.Match[str]) -> str:
        return mask_key(match.group(0))

    return _SECRET.sub(_replace, text or "")


def env_insecure_ssl() -> bool:
    value = os.environ.get(INSECURE_SSL_ENV, "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def resolve_insecure_ssl(explicit: bool | None = None) -> bool:
    return bool(explicit) or env_insecure_ssl()


def is_cert_verify_error(exc: BaseException) -> bool:
    if isinstance(exc, ssl.SSLCertVerificationError):
        return True
    reason = getattr(exc, "reason", None)
    if isinstance(reason, ssl.SSLCertVerificationError):
        return True
    parts = [str(exc)]
    if reason is not None:
        parts.append(str(reason))
    blob = " ".join(parts).lower()
    return (
        "certificate_verify_failed" in blob
        or "certificate verify failed" in blob
        or "self-signed certificate" in blob
    )


def ssl_context(insecure: bool = False) -> ssl.SSLContext:
    if insecure:
        return ssl._create_unverified_context()
    return ssl.create_default_context(cafile=certifi.where())


def get_json(
    url: str,
    headers: dict[str, str] | None = None,
    timeout: float = 15.0,
    insecure: bool = False,
) -> Any:
    req_headers = {
        "Accept": "application/json",
        "User-Agent": "agent-gate/0.2",
    }
    if headers:
        req_headers.update(headers)
    request = urllib.request.Request(url, headers=req_headers, method="GET")
    context = ssl_context(insecure=insecure)
    try:
        with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            body = ""
        raise HttpError(int(exc.code), redact(body)) from None
    except urllib.error.URLError as exc:
        if not insecure and is_cert_verify_error(exc):
            raise SslVerifyError(redact(str(getattr(exc, "reason", exc) or exc))) from None
        reason = redact(str(getattr(exc, "reason", exc) or exc))
        raise TimeoutError(reason) from None
    except ssl.SSLError as exc:
        if not insecure and is_cert_verify_error(exc):
            raise SslVerifyError(redact(str(exc))) from None
        raise TimeoutError(redact(str(exc) or "tls error")) from None
    except TimeoutError as exc:
        raise TimeoutError(redact(str(exc) or "timed out")) from None
    if not raw.strip():
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(redact(f"invalid JSON: {exc}")) from None
