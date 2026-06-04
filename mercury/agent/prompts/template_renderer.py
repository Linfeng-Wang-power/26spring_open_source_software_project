"""YAML prompt template loader and renderer.

Built-in templates live in ``resources/prompts/``. Each template is a YAML doc
with a ``messages`` list of ``{role, content}`` items and a ``variables`` list
declaring required placeholders.

The renderer does ``str.format_map`` substitution only. It does NOT mutate
content after substitution -- whatever you put in the template is what reaches
the model.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

import yaml

BUILTIN_PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "resources" / "prompts"


class PromptError(Exception):
    """Raised when a prompt template is missing, malformed, or under-rendered."""


@dataclass(frozen=True)
class PromptMessage:
    role: str
    content: str


@dataclass(frozen=True)
class PromptTemplate:
    """A parsed prompt template."""

    name: str
    version: str
    description: str
    variables: tuple[str, ...]
    messages: tuple[PromptMessage, ...]
    source_text: str = field(repr=False, default="")

    @property
    def fingerprint(self) -> str:
        """Short stable hash for tagging persisted agent results."""
        digest = hashlib.sha256(self.source_text.encode("utf-8")).hexdigest()
        return digest[:8]


@dataclass(frozen=True)
class RenderedPrompt:
    """Final messages ready to send to the provider."""

    messages: tuple[PromptMessage, ...]
    template_name: str
    template_version: str
    template_fingerprint: str


def load_template(name: str, *, search_dir: Path | None = None) -> PromptTemplate:
    """Load a built-in prompt template by name (without ``.yaml``)."""
    base = search_dir or BUILTIN_PROMPTS_DIR
    path = base / f"{name}.yaml"
    if not path.exists():
        raise PromptError(f"Prompt template not found: {path}")

    text = path.read_text(encoding="utf-8")
    try:
        data = yaml.safe_load(text) or {}
    except yaml.YAMLError as exc:
        raise PromptError(f"Invalid YAML in {path}: {exc}") from exc

    return _parse_template(name, data, source_text=text)


def render_template(
    template: PromptTemplate,
    variables: dict[str, str],
) -> RenderedPrompt:
    """Render *template* with *variables*, returning final messages.

    Missing variables raise ``PromptError``. Extra variables are ignored.
    """
    missing = [v for v in template.variables if v not in variables]
    if missing:
        raise PromptError(
            f"Missing variables for template '{template.name}': {missing}"
        )

    safe_vars = _SafeDict(variables)
    rendered_messages = tuple(
        PromptMessage(role=m.role, content=m.content.format_map(safe_vars))
        for m in template.messages
    )
    return RenderedPrompt(
        messages=rendered_messages,
        template_name=template.name,
        template_version=template.version,
        template_fingerprint=template.fingerprint,
    )


# -- Internal -----------------------------------------------------------------


class _SafeDict(dict):
    """`format_map` helper that leaves unknown placeholders untouched."""

    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def _parse_template(name: str, data: dict, *, source_text: str) -> PromptTemplate:
    if not isinstance(data, dict):
        raise PromptError(f"Prompt '{name}' must be a YAML mapping")

    raw_messages = data.get("messages")
    if not isinstance(raw_messages, list) or not raw_messages:
        raise PromptError(f"Prompt '{name}' must have a non-empty 'messages' list")

    messages: list[PromptMessage] = []
    for idx, item in enumerate(raw_messages):
        if not isinstance(item, dict):
            raise PromptError(f"Prompt '{name}' message #{idx} must be a mapping")
        role = item.get("role")
        content = item.get("content")
        if not isinstance(role, str) or not isinstance(content, str):
            raise PromptError(
                f"Prompt '{name}' message #{idx} requires string 'role' and 'content'"
            )
        messages.append(PromptMessage(role=role, content=content))

    variables = tuple(data.get("variables") or [])
    for var in variables:
        if not isinstance(var, str):
            raise PromptError(f"Prompt '{name}' variables must be strings")

    return PromptTemplate(
        name=name,
        version=str(data.get("version", "1")),
        description=str(data.get("description", "")),
        variables=variables,
        messages=tuple(messages),
        source_text=source_text,
    )
