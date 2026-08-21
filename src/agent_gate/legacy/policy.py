from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class ToolRule:
    name: str
    allow_all: bool
    allow: frozenset[str] | None
    deny: frozenset[str]
    dual_control: bool


@dataclass(frozen=True)
class Policy:
    path: Path
    roles: frozenset[str]
    tools: dict[str, ToolRule]
    max_calls_per_session: int | None

    @classmethod
    def load(cls, path: str | Path) -> Policy:
        policy_path = Path(path)
        raw = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError(f"policy must be a mapping: {policy_path}")

        roles_raw = raw.get("roles") or []
        if not isinstance(roles_raw, list) or not roles_raw:
            raise ValueError("policy.roles must be a non-empty list")
        roles = frozenset(str(r) for r in roles_raw)

        tools_raw = raw.get("tools") or {}
        if not isinstance(tools_raw, dict):
            raise ValueError("policy.tools must be a mapping")

        tools: dict[str, ToolRule] = {}
        for name, spec in tools_raw.items():
            spec = spec or {}
            if not isinstance(spec, dict):
                raise ValueError(f"tool '{name}' must be a mapping")
            raw_allow = spec.get("allow")
            allow_all = raw_allow == "all"
            allow: frozenset[str] | None
            if allow_all:
                allow = None
            elif isinstance(raw_allow, list):
                allow = frozenset(str(x) for x in raw_allow)
            elif raw_allow is None:
                allow = None
            else:
                raise ValueError(f"tool '{name}'.allow must be 'all' or a list")
            deny_raw = spec.get("deny") or []
            if not isinstance(deny_raw, list):
                raise ValueError(f"tool '{name}'.deny must be a list")
            tools[str(name)] = ToolRule(
                name=str(name),
                allow_all=allow_all,
                allow=allow,
                deny=frozenset(str(x) for x in deny_raw),
                dual_control=bool(spec.get("dual_control", False)),
            )

        budget = raw.get("budget") or {}
        if budget is None:
            budget = {}
        if not isinstance(budget, dict):
            raise ValueError("policy.budget must be a mapping")
        max_calls = budget.get("max_calls_per_session")
        if max_calls is not None:
            max_calls = int(max_calls)
            if max_calls < 0:
                raise ValueError("budget.max_calls_per_session must be >= 0")

        return cls(
            path=policy_path,
            roles=roles,
            tools=tools,
            max_calls_per_session=max_calls,
        )

    def role_decision(self, role: str, tool: str) -> tuple[bool, str]:
        if role not in self.roles:
            return False, f"unknown role '{role}'"
        rule = self.tools.get(tool)
        if rule is None:
            return False, f"unknown tool '{tool}'"
        if role in rule.deny:
            return False, f"role '{role}' is denied for tool '{tool}'"
        if rule.allow_all:
            return True, f"role '{role}' allowed to use '{tool}'"
        if rule.allow is not None:
            if role in rule.allow:
                return True, f"role '{role}' allowed to use '{tool}'"
            return False, f"role '{role}' is not allowed to use '{tool}'"
        if rule.deny:
            return True, f"role '{role}' allowed to use '{tool}'"
        return False, f"tool '{tool}' has no allow rule"


def dump_public(policy: Policy) -> dict[str, Any]:
    return {
        "path": str(policy.path),
        "roles": sorted(policy.roles),
        "tools": sorted(policy.tools),
        "max_calls_per_session": policy.max_calls_per_session,
    }
