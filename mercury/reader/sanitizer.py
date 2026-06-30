"""HTML URL repair and sanitization for reader content."""

from __future__ import annotations

from urllib.parse import urljoin

import bleach
from bs4 import BeautifulSoup


ALLOWED_TAGS = frozenset(
    {
        "a",
        "abbr",
        "blockquote",
        "br",
        "code",
        "del",
        "div",
        "em",
        "figcaption",
        "figure",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "hr",
        "img",
        "li",
        "ol",
        "p",
        "pre",
        "span",
        "strong",
        "sub",
        "sup",
        "table",
        "tbody",
        "td",
        "th",
        "thead",
        "tr",
        "ul",
    }
)

ALLOWED_ATTRIBUTES = {
    "a": ["href", "title"],
    "abbr": ["title"],
    "img": ["alt", "src", "title"],
    "th": ["colspan", "rowspan"],
    "td": ["colspan", "rowspan"],
}

ALLOWED_PROTOCOLS = frozenset({"http", "https", "mailto"})


def repair_relative_urls(html: str, base_url: str) -> str:
    """Resolve relative link and image URLs against the article base URL."""

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all("img"):
        image_url = _best_image_url(tag)
        if image_url:
            tag["src"] = urljoin(base_url, image_url)
        for lazy_attr in (
            "data-src",
            "data-original",
            "data-lazy-src",
            "data-url",
            "srcset",
            "data-srcset",
        ):
            tag.attrs.pop(lazy_attr, None)

    for tag in soup.find_all("a"):
        value = tag.get("href")
        if value:
            tag["href"] = urljoin(base_url, value)
    return str(soup)


def sanitize_html(html: str) -> str:
    """Remove unsafe tags, attributes, protocols, and inline scripts."""

    cleaned = bleach.clean(
        html,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        protocols=ALLOWED_PROTOCOLS,
        strip=True,
    )
    return bleach.linkify(cleaned, callbacks=[_external_link_callback])


def clean_reader_html(html: str, base_url: str) -> str:
    """Repair URLs first, then sanitize the resulting HTML."""

    return sanitize_html(repair_relative_urls(html, base_url))


def _external_link_callback(attrs: dict, new: bool = False) -> dict:
    href_key = (None, "href")
    if href_key in attrs:
        attrs[(None, "rel")] = "noopener noreferrer"
    return attrs


def _best_image_url(tag: object) -> str:
    for attr in ("srcset", "data-srcset"):
        value = tag.get(attr) if hasattr(tag, "get") else None
        candidate = _best_srcset_url(str(value)) if value else ""
        if candidate:
            return candidate

    for attr in ("data-src", "data-original", "data-lazy-src", "data-url", "src"):
        value = tag.get(attr) if hasattr(tag, "get") else None
        if value and not _is_placeholder_image_url(str(value)):
            return str(value).strip()

    parent = getattr(tag, "parent", None)
    while parent is not None:
        if getattr(parent, "name", "") == "picture":
            for source in parent.find_all("source"):
                for attr in ("srcset", "data-srcset"):
                    value = source.get(attr)
                    candidate = _best_srcset_url(str(value)) if value else ""
                    if candidate:
                        return candidate
            break
        parent = getattr(parent, "parent", None)
    return ""


def _best_srcset_url(srcset: str) -> str:
    candidates: list[tuple[int, str]] = []
    for item in srcset.split(","):
        parts = item.strip().split()
        if not parts or _is_placeholder_image_url(parts[0]):
            continue
        width = 0
        if len(parts) > 1 and parts[1].endswith("w"):
            width_text = parts[1][:-1]
            width = int(width_text) if width_text.isdigit() else 0
        candidates.append((width, parts[0]))
    if not candidates:
        return ""
    return max(candidates, key=lambda candidate: candidate[0])[1]


def _is_placeholder_image_url(url: str) -> bool:
    lowered = url.strip().lower()
    if not lowered or lowered.startswith("data:"):
        return True
    markers = ("placeholder", "spacer", "transparent", "blank.gif", "1x1", "pixel")
    return any(marker in lowered for marker in markers)
