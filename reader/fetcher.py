"""HTTP source HTML fetcher for reader mode."""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from reader.models import FetchResult


DEFAULT_USER_AGENT = "MercuryPyQt/0.1 (+local-first RSS reader)"


@dataclass(frozen=True)
class SourceHtmlFetcher:
    """Fetch article source HTML with redirects and timeout handling."""

    timeout_seconds: float = 15.0
    user_agent: str = DEFAULT_USER_AGENT

    def fetch(self, url: str, client: httpx.Client | None = None) -> FetchResult:
        headers = {"User-Agent": self.user_agent}
        owns_client = client is None
        active_client = client or httpx.Client(
            follow_redirects=True,
            timeout=self.timeout_seconds,
            headers=headers,
        )

        try:
            response = active_client.get(url, headers=headers)
            response.raise_for_status()
            return FetchResult(
                source_url=url,
                final_url=str(response.url),
                html=response.text,
            )
        finally:
            if owns_client:
                active_client.close()
