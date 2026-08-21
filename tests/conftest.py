from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_POLICY = ROOT / "policies" / "example.yaml"


@pytest.fixture
def policy_path() -> Path:
    return EXAMPLE_POLICY


@pytest.fixture
def audit_path(tmp_path: Path) -> Path:
    return tmp_path / "audit.jsonl"


@pytest.fixture
def gate(policy_path: Path, audit_path: Path):
    from agent_gate.legacy import Gate

    return Gate(policy_path=policy_path, audit_path=audit_path)
