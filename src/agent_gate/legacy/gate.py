from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent_gate.legacy.audit import APPROVAL, DECISION, AuditLog, as_args
from agent_gate.legacy.policy import Policy, ToolRule


DUAL_CONTROL_N = 2


@dataclass(frozen=True)
class CheckResult:
    allowed: bool
    decision: str
    reason: str
    role: str
    tool: str
    actor: str | None = None
    session: str | None = None
    approvers: tuple[str, ...] = ()
    approvals_needed: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "decision": self.decision,
            "reason": self.reason,
            "role": self.role,
            "tool": self.tool,
            "actor": self.actor,
            "session": self.session,
            "approvers": list(self.approvers),
            "approvals_needed": self.approvals_needed,
        }


class Gate:
    """Control plane around tool calls: check, then record; dual-control for writes."""

    def __init__(
        self,
        policy_path: str | Path | None = None,
        audit_path: str | Path = "audit.jsonl",
    ) -> None:
        self.policy_path = Path(policy_path) if policy_path is not None else None
        self.policy = Policy.load(self.policy_path) if self.policy_path else None
        self.audit = AuditLog(audit_path)

    def check(
        self,
        role: str,
        tool: str,
        actor: str | None = None,
        session: str | None = None,
    ) -> CheckResult:
        if self.policy is None:
            raise RuntimeError("policy is required for check")
        ok, reason = self.policy.role_decision(role, tool)
        rule = self.policy.tools.get(tool)
        approvers: tuple[str, ...] = ()
        needed = 0
        if not ok:
            return CheckResult(
                allowed=False,
                decision="deny",
                reason=reason,
                role=role,
                tool=tool,
                actor=actor,
                session=session,
                approvers=approvers,
                approvals_needed=needed,
            )

        if rule is not None and rule.dual_control:
            needed = DUAL_CONTROL_N
            if not session:
                return CheckResult(
                    allowed=False,
                    decision="deny",
                    reason=(
                        f"tool '{tool}' requires dual_control "
                        f"({DUAL_CONTROL_N} distinct approvers) and a session id"
                    ),
                    role=role,
                    tool=tool,
                    actor=actor,
                    session=session,
                    approvers=(),
                    approvals_needed=needed,
                )
            approvers = self.audit.unique_approvers(session, tool)
            if len(approvers) < DUAL_CONTROL_N:
                return CheckResult(
                    allowed=False,
                    decision="deny",
                    reason=(
                        f"tool '{tool}' requires dual_control "
                        f"({DUAL_CONTROL_N} distinct approvers; have {len(approvers)})"
                    ),
                    role=role,
                    tool=tool,
                    actor=actor,
                    session=session,
                    approvers=approvers,
                    approvals_needed=DUAL_CONTROL_N - len(approvers),
                )

        if (
            session
            and self.policy.max_calls_per_session is not None
            and self.audit.session_call_count(session)
            >= self.policy.max_calls_per_session
        ):
            count = self.audit.session_call_count(session)
            return CheckResult(
                allowed=False,
                decision="deny",
                reason=(
                    f"budget exceeded: session '{session}' has {count} calls "
                    f"(max {self.policy.max_calls_per_session})"
                ),
                role=role,
                tool=tool,
                actor=actor,
                session=session,
                approvers=approvers,
                approvals_needed=0,
            )

        return CheckResult(
            allowed=True,
            decision="allow",
            reason=reason,
            role=role,
            tool=tool,
            actor=actor,
            session=session,
            approvers=approvers,
            approvals_needed=0,
        )

    def record(
        self,
        session: str,
        actor: str,
        tool: str,
        args: Any,
        decision: str,
        role: str | None = None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        if decision not in {"allow", "deny"}:
            raise ValueError("decision must be 'allow' or 'deny'")
        return self.audit.append(
            {
                "event": DECISION,
                "session": session,
                "actor": actor,
                "tool": tool,
                "args": as_args(args),
                "decision": decision,
                "role": role or "",
                "reason": reason or "",
            }
        )

    def approve(self, session: str, tool: str, approver: str) -> dict[str, Any]:
        approver = str(approver).strip()
        if not approver:
            raise ValueError("approver id is required")
        self.audit.append(
            {
                "event": APPROVAL,
                "session": session,
                "tool": tool,
                "approver": approver,
            }
        )
        unique = self.audit.unique_approvers(session, tool)
        return {
            "session": session,
            "tool": tool,
            "approver": approver,
            "unique_approvers": list(unique),
            "count": len(unique),
            "dual_control_met": len(unique) >= DUAL_CONTROL_N,
        }

    def export_audit(self, from_ts: str, out: str | Path) -> Path:
        return self.audit.export_csv(out=out, from_ts=from_ts)

    def tool_rule(self, tool: str) -> ToolRule | None:
        if self.policy is None:
            return None
        return self.policy.tools.get(tool)
