from __future__ import annotations

from pathlib import Path


def test_export_csv_nonempty(gate, tmp_path: Path) -> None:
    gate.record(
        session="S",
        actor="a",
        tool="read_file",
        args={},
        decision="allow",
        role="intern",
    )
    out = tmp_path / "audit.csv"
    gate.export_audit(from_ts="2020-01-01", out=out)
    assert out.exists()
    assert out.stat().st_size > 0
    text = out.read_text(encoding="utf-8")
    assert "read_file" in text
    assert "allow" in text
    header = text.splitlines()[0]
    assert "timestamp" in header
    assert "tool" in header


def test_export_from_filters_old_rows(gate, tmp_path: Path) -> None:
    gate.record(
        session="S",
        actor="a",
        tool="read_file",
        args={},
        decision="allow",
        role="intern",
    )
    out = tmp_path / "empty.csv"
    gate.export_audit(from_ts="2099-01-01", out=out)
    lines = [ln for ln in out.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 1  # header only
