from __future__ import annotations

import csv
import fcntl
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator


DECISION = "decision"
APPROVAL = "approval"

CSV_FIELDS = [
    "timestamp",
    "event",
    "session",
    "actor",
    "role",
    "tool",
    "decision",
    "reason",
    "approver",
    "args",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_ts(value: str) -> datetime:
    text = value.strip()
    if len(text) == 10 and text[4] == "-" and text[7] == "-":
        return datetime.fromisoformat(text).replace(tzinfo=timezone.utc)
    dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


class AuditLog:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def append(self, event: dict[str, Any]) -> dict[str, Any]:
        row = {"timestamp": utc_now(), **event}
        line = json.dumps(row, ensure_ascii=False, default=str)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            handle.write(line + "\n")
            handle.flush()
        return row

    def iter_events(self) -> Iterator[dict[str, Any]]:
        if not self.path.exists():
            return
        with self.path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(row, dict):
                    yield row

    def unique_approvers(self, session: str, tool: str) -> tuple[str, ...]:
        seen: list[str] = []
        for row in self.iter_events():
            if row.get("event") != APPROVAL:
                continue
            if row.get("session") != session or row.get("tool") != tool:
                continue
            approver = str(row.get("approver") or "")
            if approver and approver not in seen:
                seen.append(approver)
        return tuple(seen)

    def session_call_count(self, session: str) -> int:
        n = 0
        for row in self.iter_events():
            if row.get("event") == DECISION and row.get("session") == session:
                n += 1
        return n

    def export_csv(self, out: str | Path, from_ts: str) -> Path:
        start = parse_ts(from_ts)
        out_path = Path(out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, extrasaction="ignore")
            writer.writeheader()
            for row in self.iter_events():
                raw_ts = str(row.get("timestamp") or "")
                try:
                    ts = parse_ts(raw_ts)
                except ValueError:
                    continue
                if ts < start:
                    continue
                writer.writerow(
                    {
                        "timestamp": raw_ts,
                        "event": row.get("event", ""),
                        "session": row.get("session", ""),
                        "actor": row.get("actor", ""),
                        "role": row.get("role", ""),
                        "tool": row.get("tool", ""),
                        "decision": row.get("decision", ""),
                        "reason": row.get("reason", ""),
                        "approver": row.get("approver", ""),
                        "args": _args_cell(row.get("args")),
                    }
                )
        return out_path

    def last_decisions(self, limit: int = 20) -> list[dict[str, Any]]:
        rows = [row for row in self.iter_events() if row.get("event") == DECISION]
        return rows[-limit:]


def _args_cell(value: Any) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def as_args(value: Any) -> Any:
    if value is None:
        return {}
    if isinstance(value, str):
        text = value.strip() or "{}"
        return json.loads(text)
    if isinstance(value, dict):
        return value
    raise TypeError("args must be a dict or JSON object string")


def iter_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    return AuditLog(path).iter_events()
