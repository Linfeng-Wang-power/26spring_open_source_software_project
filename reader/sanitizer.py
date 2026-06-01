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
    for tag_name, attribute in (("a", "href"), ("img", "src")):
        for tag in soup.find_all(tag_name):
            value = tag.get(attribute)
            if value:
                tag[attribute] = urljoin(base_url, value)
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
