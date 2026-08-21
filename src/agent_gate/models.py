from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

OPENAI_PERSONAL_KEY_MSG = "该平台个人 Key 无法按把查询月度账单，需要组织 Admin Key"


def format_amount(value: float | int | str | None, unit: str) -> str | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        text = str(value).strip()
        unit_text = (unit or "").strip()
        return f"{text} {unit_text}".strip() if text else None
    if abs(number - round(number)) < 1e-9:
        text = str(int(round(number)))
    else:
        text = f"{number:.6f}".rstrip("0").rstrip(".")
    unit_text = (unit or "").strip()
    return f"{text} {unit_text}".strip()


@dataclass
class UsageRow:
    masked: str
    provider: str
    used: str | None = None
    remaining: str | None = None
    cost: str | None = None
    note: str | None = None
    error: str | None = None
    used_value: float | None = None
    used_unit: str | None = None
    remaining_value: float | None = None
    remaining_unit: str | None = None
    cost_value: float | None = None
    cost_unit: str | None = None

    def display_amount(self) -> str | None:
        if self.provider == "deepseek":
            return self.remaining
        parts: list[str] = []
        if self.used:
            parts.append(f"已用 {self.used}")
        if self.remaining:
            parts.append(f"剩余 {self.remaining}")
        return "；".join(parts) if parts else None

    def as_dict(self) -> dict[str, Any]:
        amount = self.display_amount()
        return {
            "masked": self.masked,
            "provider": self.provider,
            "used": self.used,
            "remaining": self.remaining,
            "amount": amount,
            "balance": self.remaining if self.provider == "deepseek" else None,
            "cost": self.cost,
            "note": self.note,
            "error": self.error,
        }


@dataclass
class UsageReport:
    rows: list[UsageRow]
    totals: dict[str, str]
    from_date: date
    to_date: date
    totals_label: str = "合计"
    totals_note: str = ""
    subtotals: list[dict[str, str]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": True,
            "from": self.from_date.isoformat(),
            "to": self.to_date.isoformat(),
            "rows": [row.as_dict() for row in self.rows],
            "totals": dict(self.totals),
            "totals_label": self.totals_label,
            "totals_note": self.totals_note,
            "subtotals": list(self.subtotals),
        }
