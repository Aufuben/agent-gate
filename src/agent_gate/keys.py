from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

PROVIDERS = ("openrouter", "deepseek", "openai")

ALIASES = {
    "openrouter": "openrouter",
    "or": "openrouter",
    "deepseek": "deepseek",
    "ds": "deepseek",
    "openai": "openai",
    "oa": "openai",
}


@dataclass(frozen=True)
class ParsedKey:
    provider: str
    secret: str
    masked: str
    line: int
    error: str | None = None


def mask_key(secret: str) -> str:
    text = (secret or "").strip()
    if len(text) <= 8:
        return "****"
    if text.startswith("sk-or-"):
        prefix = "sk-or-"
    elif text.startswith("sk-proj-"):
        prefix = "sk-proj-"
    elif text.startswith("sk-admin-"):
        prefix = "sk-admin-"
    elif text.startswith("sk-"):
        prefix = "sk-"
    else:
        prefix = text[:3]
    return f"{prefix}...{text[-4:]}"


def detect_provider(secret: str, allowed: set[str]) -> str | None:
    if secret.startswith("sk-or-"):
        return "openrouter"
    if secret.startswith("sk-admin-") or secret.startswith("sk-proj-"):
        return "openai"
    if secret.startswith("sk-"):
        candidates = [name for name in ("openai", "deepseek") if name in allowed]
        if len(candidates) == 1:
            return candidates[0]
        return None
    return None


def parse_keys(
    text: str,
    providers: Sequence[str] | Iterable[str] | None = None,
) -> list[ParsedKey]:
    allowed = tuple(providers) if providers is not None else PROVIDERS
    allowed_set = set(allowed)
    rows: list[ParsedKey] = []
    for index, raw in enumerate((text or "").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        provider: str | None = None
        secret = line
        if ":" in line:
            left, right = line.split(":", 1)
            alias = left.strip().lower()
            if alias in ALIASES:
                provider = ALIASES[alias]
                secret = right.strip()
        secret = secret.strip()
        masked = mask_key(secret) if secret else "****"
        if not secret:
            rows.append(
                ParsedKey(provider=provider or "", secret="", masked=masked, line=index, error="空密钥")
            )
            continue
        if provider is None:
            provider = detect_provider(secret, allowed_set)
        if provider is None:
            rows.append(
                ParsedKey(
                    provider="",
                    secret=secret,
                    masked=masked,
                    line=index,
                    error="无法自动识别，请写成 openai:sk-... 或 deepseek:sk-...",
                )
            )
            continue
        if provider not in allowed_set:
            rows.append(
                ParsedKey(
                    provider=provider,
                    secret=secret,
                    masked=masked,
                    line=index,
                    error=f"未选择该平台（{provider}）",
                )
            )
            continue
        rows.append(
            ParsedKey(provider=provider, secret=secret, masked=masked, line=index)
        )
    return rows
