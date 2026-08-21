from __future__ import annotations

from agent_gate.keys import mask_key, parse_keys


def test_mask_key_keeps_prefix_and_last_four() -> None:
    assert mask_key("sk-abcdefghijklmnopqrstuvwxyz") == "sk-...wxyz"
    assert mask_key("sk-or-v1-abcdefghijklmnopqrstuvwxyz") == "sk-or-...wxyz"


def test_parse_provider_prefix() -> None:
    rows = parse_keys(
        "openrouter:sk-or-v1-abcdefghijklmnopqrstuvwxyz\n"
        "deepseek:sk-1234567890abcdef\n"
        "openai:sk-proj-abcdefghijklmnopqrstuvwxyz\n"
    )
    assert [r.provider for r in rows] == ["openrouter", "deepseek", "openai"]
    assert all(r.error is None for r in rows)
    assert rows[0].secret.startswith("sk-or-")
    assert rows[0].masked == "sk-or-...wxyz"


def test_auto_detect_openrouter_prefix() -> None:
    rows = parse_keys("sk-or-v1-abcdefghijklmnopqrstuvwxyz\n")
    assert rows[0].provider == "openrouter"
    assert rows[0].error is None


def test_bare_sk_is_ambiguous_when_openai_and_deepseek_selected() -> None:
    rows = parse_keys("sk-1234567890abcdef\n", providers=("openrouter", "deepseek", "openai"))
    assert rows[0].error
    assert "openai:" in rows[0].error
    assert "deepseek:" in rows[0].error


def test_bare_sk_uses_only_selected_provider() -> None:
    rows = parse_keys("sk-1234567890abcdef\n", providers=("deepseek",))
    assert rows[0].provider == "deepseek"
    assert rows[0].error is None


def test_sk_proj_is_openai() -> None:
    rows = parse_keys("sk-proj-abcdefghijklmnopqrstuvwxyz\n")
    assert rows[0].provider == "openai"


def test_sk_admin_is_openai() -> None:
    rows = parse_keys("sk-admin-abcdefghijklmnopqrstuvwxyz\n")
    assert rows[0].provider == "openai"


def test_skip_blank_and_comment_lines() -> None:
    rows = parse_keys("# comment\n\n  \nopenrouter:sk-or-v1-abcdefghijklmnopqrstuvwxyz\n")
    assert len(rows) == 1
    assert rows[0].provider == "openrouter"
