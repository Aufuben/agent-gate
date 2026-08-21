from __future__ import annotations

from collections.abc import Callable

from agent_gate.keys import ParsedKey
from agent_gate.models import UsageRow
from agent_gate.providers.deepseek import query_deepseek
from agent_gate.providers.openai import query_openai
from agent_gate.providers.openrouter import query_openrouter

HttpGet = Callable[..., object]
Handler = Callable[..., UsageRow]

HANDLERS: dict[str, Handler] = {
    "openrouter": query_openrouter,
    "deepseek": query_deepseek,
    "openai": query_openai,
}

__all__ = ["HANDLERS", "HttpGet", "ParsedKey", "query_deepseek", "query_openai", "query_openrouter"]
