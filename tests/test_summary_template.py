"""Tests for the YAML prompt template loader/renderer."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent.prompts.template_renderer import (
    PromptError,
    load_template,
    render_template,
)


def test_load_builtin_summary_template() -> None:
    template = load_template("summary.default")
    assert template.name == "summary.default"
    assert "target_language" in template.variables
    assert "detail_level" in template.variables
    assert "title" in template.variables
    assert "content" in template.variables
    assert template.fingerprint  # 8 hex chars
    assert len(template.fingerprint) == 8
    # System + user
    roles = [m.role for m in template.messages]
    assert "system" in roles
    assert "user" in roles


def test_render_substitutes_variables() -> None:
    template = load_template("summary.default")
    rendered = render_template(
        template,
        {
            "target_language": "zh-CN",
            "detail_level": "short",
            "title": "Hello",
            "content": "World content",
        },
    )
    full = "\n".join(m.content for m in rendered.messages)
    assert "zh-CN" in full
    assert "short" in full
    assert "World content" in full
    assert rendered.template_name == "summary.default"
    assert rendered.template_fingerprint == template.fingerprint


def test_render_missing_variable_raises() -> None:
    template = load_template("summary.default")
    with pytest.raises(PromptError):
        render_template(template, {"title": "x", "content": "y"})


def test_load_missing_template_raises(tmp_path: Path) -> None:
    with pytest.raises(PromptError):
        load_template("does_not_exist", search_dir=tmp_path)


def test_invalid_yaml_raises(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("messages: [unterminated\n", encoding="utf-8")
    with pytest.raises(PromptError):
        load_template("bad", search_dir=tmp_path)


def test_template_without_messages_raises(tmp_path: Path) -> None:
    bad = tmp_path / "empty.yaml"
    bad.write_text("name: empty\nversion: '1'\n", encoding="utf-8")
    with pytest.raises(PromptError):
        load_template("empty", search_dir=tmp_path)


def test_fingerprint_changes_with_content(tmp_path: Path) -> None:
    a = tmp_path / "a.yaml"
    b = tmp_path / "b.yaml"
    a.write_text(
        "version: '1'\nvariables: []\nmessages:\n  - role: user\n    content: A\n",
        encoding="utf-8",
    )
    b.write_text(
        "version: '1'\nvariables: []\nmessages:\n  - role: user\n    content: B\n",
        encoding="utf-8",
    )
    assert load_template("a", search_dir=tmp_path).fingerprint != load_template(
        "b", search_dir=tmp_path
    ).fingerprint
