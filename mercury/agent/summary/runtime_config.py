"""Bootstrap a runtime SummaryAgent.

Reads provider config from a SettingsStore (preferred) or environment vars
as a fallback. API keys come from keyring first, env second.

Settings keys (all under SettingsStore):
- ``llm.base_url``     : OpenAI-compatible endpoint root
- ``llm.model``        : model identifier
- ``summary.detail``   : "short" | "default" | "detailed"

Environment fallbacks:
- ``MERCURY_LLM_BASE_URL``, ``MERCURY_LLM_MODEL``
- ``OPENAI_API_KEY``  (only when keyring is empty)
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Protocol

from mercury.agent.provider.keys import resolve_api_key
from mercury.agent.provider.llm_provider import ProviderConfig
from mercury.agent.provider.openai_compatible import OpenAICompatibleProvider
from mercury.agent.summary.summary_agent import SummaryAgent


class _SettingsLike(Protocol):
    def get(self, key: str, default: str = "") -> str: ...


@dataclass(frozen=True)
class RuntimeStatus:
    """Why a runtime could or could not be built."""

    ok: bool
    reason: str = ""


def build_runtime(
    settings: _SettingsLike | None = None,
) -> tuple[SummaryAgent | None, RuntimeStatus]:
    """Return (agent, status). On failure, agent is None and status.reason is shown."""
    base_url = ""
    model = ""
    if settings is not None:
        base_url = (settings.get("llm.base_url", "") or "").strip()
        model = (settings.get("llm.model", "") or "").strip()
    if not base_url:
        base_url = os.environ.get("MERCURY_LLM_BASE_URL", "").strip()
    if not model:
        model = os.environ.get("MERCURY_LLM_MODEL", "").strip()
    api_key = resolve_api_key()

    missing = []
    if not base_url:
        missing.append("Base URL")
    if not model:
        missing.append("Model")
    if not api_key:
        missing.append("API Key")
    if missing:
        return None, RuntimeStatus(False, "缺少配置: " + ", ".join(missing))

    config = ProviderConfig(base_url=base_url, model=model, api_key=api_key)
    provider = OpenAICompatibleProvider(config)
    agent = SummaryAgent(provider)
    return agent, RuntimeStatus(True)
