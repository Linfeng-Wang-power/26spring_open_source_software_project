"""Readable article extraction."""

from __future__ import annotations

from bs4 import BeautifulSoup
from bs4.element import Tag
from readability import Document

from mercury.reader.models import ReadabilityResult

NO_TITLE = "[no-title]"


def extract_readable_html(source_html: str) -> ReadabilityResult:
    """Extract main article HTML using readability-lxml."""

    document = Document(source_html)
    title = _best_title(source_html, document)
    content_html = _best_content_html(source_html, document.summary(html_partial=True))
    return ReadabilityResult(title=title, content_html=content_html)


def _best_title(source_html: str, document: Document) -> str:
    readability_title = (document.short_title() or document.title() or "").strip()
    if _is_usable_title(readability_title):
        return readability_title

    soup = BeautifulSoup(source_html, "html.parser")
    for tag in (
        soup.find("meta", {"property": "og:title"}),
        soup.find("meta", {"name": "twitter:title"}),
        soup.find("h1"),
        soup.find("title"),
    ):
        if tag is None:
            continue
        value = tag.get("content", "") if tag.name == "meta" else tag.get_text(" ", strip=True)
        value = value.strip()
        if _is_usable_title(value):
            return value

    return "Untitled"


def _is_usable_title(title: str) -> bool:
    normalized = title.strip().lower()
    return bool(normalized and normalized != NO_TITLE)


def _best_content_html(source_html: str, readability_html: str) -> str:
    soup = BeautifulSoup(source_html, "html.parser")
    candidates = [readability_html]

    bbc_html = _extract_bbc_content_html(soup)
    if bbc_html:
        return bbc_html

    for tag in _content_candidate_tags(soup):
        candidates.append(str(tag))

    return max(candidates, key=_content_score)


def _text_length(html: str) -> int:
    return len(BeautifulSoup(html, "html.parser").get_text(" ", strip=True))


def _content_candidate_tags(soup: BeautifulSoup) -> list[Tag]:
    candidates: list[Tag] = []
    candidates.extend(soup.find_all("article"))
    candidates.extend(soup.find_all("main"))
    candidates.extend(soup.find_all(attrs={"role": "main"}))
    return candidates


def _extract_bbc_content_html(soup: BeautifulSoup) -> str:
    if not _looks_like_bbc_page(soup):
        return ""

    root = soup.find("article") or soup.find("main") or soup.find(attrs={"role": "main"})
    if not isinstance(root, Tag):
        return ""

    output = BeautifulSoup("<article></article>", "html.parser")
    article = output.article
    if article is None:
        return ""

    seen_text: set[str] = set()
    for tag in root.find_all(["p", "blockquote", "figure", "aside", "section"]):
        if tag.name in {"aside", "section"} and _is_non_article_container(tag):
            continue
        if tag.name == "figure":
            figure = _clean_figure(tag)
            if figure is not None:
                article.append(figure)
                caption = figure.find("figcaption")
                if caption is not None:
                    seen_text.add(_clean_caption_text(_normalized_text(caption)))
            continue

        if _is_non_article_container(tag):
            continue
        if tag.find_parent("figure") or _has_non_article_parent(tag) or not _is_content_tag(tag):
            continue
        text = tag.get_text(" ", strip=True)
        normalized_text = " ".join(text.split())
        if not normalized_text or normalized_text in seen_text:
            continue
        seen_text.add(normalized_text)
        article.append(BeautifulSoup(str(tag), "html.parser"))

    html = str(article)
    return html if _effective_paragraph_count(html) >= 3 else ""


def _clean_figure(tag: Tag) -> Tag | None:
    image = tag.find("img")
    caption = tag.find("figcaption")
    image_url = _best_figure_image_url(tag, image)
    if not image_url:
        return None

    output = BeautifulSoup("<figure></figure>", "html.parser")
    figure = output.figure
    if figure is None:
        return None

    caption_text = _clean_caption_text(_normalized_text(caption)) if caption is not None else ""
    clean_image = output.new_tag("img")
    clean_image["src"] = image_url
    clean_image["alt"] = (image.get("alt") if image is not None else "") or _caption_alt(caption_text)
    figure.append(clean_image)
    if caption_text:
        clean_caption = output.new_tag("figcaption")
        clean_caption.string = f"__MERCURY_IMAGE_CAPTION__ {caption_text}"
        figure.append(clean_caption)

    return figure


def _best_figure_image_url(figure: Tag, image: Tag | None) -> str:
    candidates: list[tuple[int, str]] = []
    if image is not None:
        for attr in ("src", "data-src", "data-original", "data-lazy-src", "data-url"):
            value = image.get(attr)
            candidate = _normalize_image_url(str(value), 1024) if value else ""
            if candidate:
                candidates.append((1024, candidate))
        for attr in ("srcset", "data-srcset"):
            candidates.extend(_srcset_candidates(str(image.get(attr, ""))))

    for source in figure.find_all("source"):
        for attr in ("srcset", "data-srcset"):
            candidates.extend(_srcset_candidates(str(source.get(attr, ""))))
    if not candidates:
        return ""
    return max(candidates, key=lambda candidate: candidate[0])[1]


def _best_srcset_url(srcset: str) -> str:
    candidates = _srcset_candidates(srcset)
    if not candidates:
        return ""
    return max(candidates, key=lambda candidate: candidate[0])[1]


def _srcset_candidates(srcset: str) -> list[tuple[int, str]]:
    candidates: list[tuple[int, str]] = []
    for item in srcset.split(","):
        parts = item.strip().split()
        if not parts:
            continue
        width = 0
        if len(parts) > 1 and parts[1].endswith("w"):
            width_text = parts[1][:-1]
            width = int(width_text) if width_text.isdigit() else 0
        candidate = _normalize_image_url(parts[0], width or 1024)
        if candidate:
            candidates.append((width, candidate))
    return candidates


def _normalize_image_url(url: str, width: int) -> str:
    stripped = url.strip()
    if not stripped or stripped.startswith("data:") or _is_placeholder_image_url(stripped):
        return ""
    chosen_width = max(width, 640)
    stripped = stripped.replace("{width}", str(chosen_width))
    stripped = stripped.replace("{height}", "0")
    return stripped if "{" not in stripped and "}" not in stripped else ""


def _is_placeholder_image_url(url: str) -> bool:
    lowered = url.strip().lower()
    markers = ("placeholder", "spacer", "transparent", "blank.gif", "1x1", "pixel")
    return any(marker in lowered for marker in markers)


def _caption_alt(caption_text: str) -> str:
    words = caption_text.split()
    return " ".join(words[:14]) if words else "Article image"


def _clean_caption_text(text: str) -> str:
    cleaned = _caption_after_marker(text)
    cleaned = cleaned.removeprefix("__MERCURY_IMAGE_CAPTION__").strip(" ,:")
    cleaned = _strip_leading_label(cleaned)
    cleaned = _strip_leading_label(cleaned)
    return cleaned


def _caption_after_marker(text: str) -> str:
    normalized = " ".join(text.split()).strip(" ,:")
    lowered = normalized.lower()
    markers = ("image caption,", "image caption:", "image caption ")
    marker_positions = [(lowered.rfind(marker), marker) for marker in markers]
    position, marker = max(marker_positions, key=lambda item: item[0])
    if position >= 0:
        return normalized[position + len(marker) :].strip(" ,:")
    return normalized


def _strip_leading_label(text: str) -> str:
    normalized = " ".join(text.split()).strip(" ,:")
    lowered = normalized.lower()
    prefixes = (
        "image caption",
        "caption",
        "image source",
        "source",
    )
    for prefix in prefixes:
        if lowered == prefix:
            return ""
        for separator in (",", ":"):
            marker = f"{prefix}{separator}"
            if lowered.startswith(marker):
                return normalized[len(marker) :].strip(" ,:")
        if lowered.startswith(prefix + " "):
            return normalized[len(prefix) :].strip(" ,:")
    return normalized


def _looks_like_bbc_page(soup: BeautifulSoup) -> bool:
    for tag in soup.find_all("meta"):
        value = " ".join(str(tag.get(attr, "")) for attr in ("content", "property", "name"))
        if "bbc.co.uk" in value or "bbc.com" in value or "BBC" in value:
            return True
    return bool(soup.find(attrs={"data-component": "text-block"}))


def _is_content_tag(tag: Tag) -> bool:
    if tag.find_parent(["nav", "header", "footer", "aside", "form"]):
        return False
    if tag.find_parent(attrs={"role": "navigation"}):
        return False
    text = tag.get_text(" ", strip=True)
    if len(text) < 12:
        return False
    if _is_noise_text(text):
        return False
    lowered = text.lower()
    return not any(phrase in lowered for phrase in ("share this", "more on this story", "related internet links"))


def _is_non_article_container(tag: Tag) -> bool:
    text = _normalized_text(tag).lower()
    markers = (
        "related internet links",
        "more on this story",
        "related links",
        "share this",
        "follow bbc",
    )
    return any(marker in text for marker in markers)


def _has_non_article_parent(tag: Tag) -> bool:
    parent = tag.find_parent()
    while isinstance(parent, Tag):
        if parent.name in {"aside", "section", "div"} and _is_non_article_container(parent):
            return True
        parent = parent.find_parent()
    return False


def _normalized_text(tag: Tag | None) -> str:
    return " ".join(tag.get_text(" ", strip=True).split()) if tag is not None else ""


def _is_noise_text(text: str) -> bool:
    normalized = " ".join(text.split()).strip()
    lowered = normalized.lower()
    compact = "".join(character for character in lowered if character.isalnum())
    noise_phrases = (
        "by",
        "published",
        "updated",
        "imagesource",
        "imagecaption",
        "sharethis",
        "readmore",
        "moreonthisstory",
        "relatedtopics",
        "followbbc",
        "listentothisarticle",
    )
    return any(compact.startswith(phrase) for phrase in noise_phrases)


def _content_score(html: str) -> float:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(["script", "style", "nav", "header", "footer", "aside", "form", "button", "svg"]):
        tag.decompose()

    text = soup.get_text(" ", strip=True)
    text_length = len(text)
    if text_length == 0:
        return 0

    effective_paragraphs = _effective_paragraph_count(str(soup))
    headings = len(soup.find_all(["h1", "h2", "h3"]))
    link_text_length = sum(len(link.get_text(" ", strip=True)) for link in soup.find_all("a"))
    link_density = link_text_length / text_length
    lowered = text.lower()
    noise_count = sum(
        lowered.count(phrase)
        for phrase in (
            "share this",
            "read more",
            "more on this story",
            "related topics",
            "advertisement",
        )
    )

    return text_length + effective_paragraphs * 250 + headings * 80 - link_density * 500 - noise_count * 150


def _effective_paragraph_count(html: str) -> int:
    soup = BeautifulSoup(html, "html.parser")
    return sum(
        1
        for tag in soup.find_all(["p", "blockquote"])
        if len(tag.get_text(" ", strip=True)) >= 40
    )
