"""Render canonical Markdown into reader-safe HTML."""

from __future__ import annotations

from html import escape

from bs4 import BeautifulSoup, NavigableString
from markdown_it import MarkdownIt

from mercury.reader.sanitizer import sanitize_html


CLEANED_READER_CSS = """
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif;
  color: #202124;
  background: #fbfaf7;
  margin: 0;
  padding: 0;
  line-height: 1.78;
  font-size: 20px;
}
.reader-header {
  width: 100%;
  max-width: none;
  margin-left: auto;
  margin-right: auto;
  padding-left: 10px;
  padding-right: 10px;
  box-sizing: border-box;
}
.reader-body {
  max-width: 1040px;
  margin-left: auto;
  margin-right: auto;
  padding-left: 0;
  padding-right: 0;
}
h1 {
  margin: 0 auto 12px auto;
  font-size: 40px;
  line-height: 1.22;
  font-weight: 800;
  letter-spacing: 0;
  text-align: center;
  color: #171717;
}
.meta {
  margin: 0 auto 38px auto;
  color: #8c9198;
  font-size: 13px;
  line-height: 1.45;
  text-align: center;
  word-break: break-all;
}
h2,
h3 {
  margin: 34px 0 14px 0;
  line-height: 1.32;
  color: #1f2328;
}
h2 {
  font-size: 25px;
  border-bottom: 1px solid #e7e2d8;
  padding-bottom: 8px;
}
h3 {
  font-size: 21px;
}
p {
  margin: 0 0 20px 0;
  font-size: 20px;
  line-height: 1.82;
}
a {
  color: #2667a6;
  text-decoration: none;
  border-bottom: 1px solid rgba(38, 103, 166, 0.28);
}
a:hover {
  color: #174a7c;
  border-bottom-color: rgba(23, 74, 124, 0.55);
}
img {
  display: block;
  width: 760px;
  max-width: 760px;
  height: auto;
  margin: 24px auto 6px auto;
  border-radius: 6px;
}
.image-caption {
  display: block;
  margin: 0 auto 18px auto;
  max-width: 740px;
  color: #7b8088;
  font-size: 14px;
  line-height: 1.48;
  text-align: center;
}
pre {
  overflow-x: auto;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  padding: 16px;
  background: #f2f0ea;
  border: 1px solid #e4ded3;
  border-radius: 6px;
}
code {
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
  font-size: 0.92em;
}
p code,
li code {
  background: #f1eee8;
  border-radius: 4px;
  padding: 2px 5px;
}
blockquote {
  margin: 28px 0;
  padding: 4px 0 4px 18px;
  border-left: 4px solid #c8bfae;
  color: #5b6067;
}
ul,
ol {
  padding-left: 26px;
  margin: 0 0 20px 0;
}
li {
  margin: 6px 0;
}
table {
  border-collapse: collapse;
  width: 100%;
  margin: 24px 0;
  font-size: 15px;
}
td,
th {
  border: 1px solid #ddd7cb;
  padding: 8px 10px;
}
th {
  background: #f1eee8;
}
"""


PLAIN_READER_CSS = """
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif;
  color: #202124;
  background: #ffffff;
  margin: 0;
  padding: 34px 80px 80px 80px;
  line-height: 1.72;
  font-size: 18px;
}
h1 {
  font-size: 34px;
  line-height: 1.18;
  margin: 0 0 18px 0;
  font-weight: 700;
  letter-spacing: 0;
}
.meta {
  color: #555;
  font-size: 15px;
  margin-bottom: 28px;
  word-break: break-all;
}
a {
  color: #2458a6;
}
img {
  display: block;
  width: 100%;
  max-width: 680px;
  height: auto;
  margin: 18px auto 6px auto;
}
.image-caption {
  display: block;
  color: #666;
  font-size: 14px;
  line-height: 1.45;
  margin: 0 auto 16px auto;
  max-width: 660px;
  text-align: center;
}
pre {
  overflow-x: auto;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  padding: 14px;
  background: #f6f8fa;
}
blockquote {
  margin-left: 0;
  padding-left: 18px;
  border-left: 4px solid #d0d7de;
  color: #57606a;
}
table {
  border-collapse: collapse;
  width: 100%;
}
td,
th {
  border: 1px solid #d0d7de;
  padding: 6px 8px;
}
"""


def render_markdown_to_reader_html(
    markdown: str,
    *,
    title: str,
    source_url: str = "",
    css: str | None = None,
    polished: bool = True,
) -> str:
    """Render Markdown to a complete HTML document for QTextBrowser/QWebEngineView."""

    active_css = css or (CLEANED_READER_CSS if polished else PLAIN_READER_CSS)
    markdown_renderer = MarkdownIt("commonmark", {"html": False}).enable("table")
    body_html = _style_reader_blocks(sanitize_html(markdown_renderer.render(markdown)), title=title)
    metadata = _render_source_link(source_url)

    return f"""<!doctype html>
<html>
  <head>
    <meta charset="utf-8">
    <style>{active_css}</style>
  </head>
  <body style="margin:0;padding:0;background:#fbfaf7;color:#202124;">
    <table width="100%" border="0" cellspacing="0" cellpadding="0" style="width:100%;border-collapse:collapse;border:0;">
      <tr>
        <td width="10" style="border:0;width:10px;">&nbsp;</td>
        <td valign="top" style="border:0;padding:46px 0 88px 0;">
          <header class="reader-header" style="width:100%;max-width:none;margin-left:auto;margin-right:auto;padding-left:10px;padding-right:10px;box-sizing:border-box;">
            <h1 style="width:100%;max-width:none;margin:0 auto 12px auto;font-size:40px;line-height:1.22;font-weight:800;text-align:center;color:#171717;">{escape(title)}</h1>
            {metadata}
          </header>
          <article class="reader-body" style="max-width:1040px;margin-left:auto;margin-right:auto;padding:0;">
            {body_html}
          </article>
        </td>
        <td width="10" style="border:0;width:10px;">&nbsp;</td>
      </tr>
    </table>
  </body>
</html>
"""


def _render_source_link(source_url: str) -> str:
    if not source_url:
        return ""

    safe_url = escape(source_url, quote=True)
    return (
        '<div class="meta" style="margin:0 auto 38px auto;color:#8c9198;font-size:13px;line-height:1.45;text-align:center;word-break:break-all;">'
        f'<a href="{safe_url}" rel="noopener noreferrer">查看原文</a>'
        f"<br>{escape(source_url)}"
        "</div>"
    )


def _style_reader_blocks(html: str, *, title: str = "") -> str:
    soup = BeautifulSoup(html, "html.parser")
    title_key = _text_key(title)
    title_words = _word_keys(title)
    for heading in soup.find_all(["h1", "h2"]):
        if _is_duplicate_heading(heading.get_text(" ", strip=True), title_key, title_words):
            heading.decompose()

    for pre in list(soup.find_all("pre")):
        text = pre.get_text("\n", strip=False).strip("\n")
        if not _looks_like_prose_code_block(text):
            continue
        replacement = soup.new_tag("div")
        for block in [part.strip() for part in text.split("\n\n") if part.strip()]:
            paragraph = soup.new_tag("p")
            paragraph.string = " ".join(line.strip() for line in block.splitlines())
            replacement.append(paragraph)
        pre.replace_with(replacement)

    previous_text = ""
    next_paragraph_is_caption = False
    for paragraph in soup.find_all("p"):
        text = paragraph.get_text(" ", strip=True)
        if paragraph.find("img"):
            _remove_direct_text(paragraph)
            paragraph["align"] = "center"
            paragraph["style"] = "text-align:center;margin:24px 0 6px 0;"
            previous_text = ""
            continue
        if _is_noise_text(text):
            paragraph.decompose()
            continue

        caption = _caption_text(text)
        if _is_caption_label(text):
            paragraph.decompose()
            next_paragraph_is_caption = True
            continue

        if not caption and next_paragraph_is_caption:
            caption = text
            next_paragraph_is_caption = False

        if not caption:
            paragraph["style"] = "margin:0 0 22px 0;font-size:20px;line-height:1.82;color:#202124;"
            previous_text = text
            continue
        if caption == previous_text:
            paragraph.decompose()
            continue
        paragraph.name = "div"
        paragraph["class"] = "image-caption"
        paragraph["align"] = "center"
        paragraph.string = caption
        previous_text = caption
    for item in soup.find_all("li"):
        if _is_noise_text(item.get_text(" ", strip=True)):
            item.decompose()
    for list_tag in soup.find_all(["ul", "ol"]):
        if not list_tag.find("li"):
            list_tag.decompose()
    for image in soup.find_all("img"):
        image["width"] = "760"
        image["style"] = "display:block;width:760px;max-width:100%;height:auto;margin:0 auto 6px auto;"
        parent = image.parent
        if parent is not None and getattr(parent, "name", "") in {"p", "div"}:
            parent["align"] = "center"
            parent["style"] = "text-align:center;margin:24px 0 6px 0;"
    for caption in soup.find_all(class_="image-caption"):
        caption["style"] = (
            "display:block;max-width:740px;margin:0 auto 18px auto;"
            "color:#7b8088;font-size:14px;line-height:1.48;text-align:center;"
        )
    return str(soup)


def _looks_like_prose_code_block(text: str) -> bool:
    stripped = text.strip()
    if not stripped or "\t" in stripped:
        return False
    lowered = stripped.lower()
    code_markers = (
        "def ",
        "class ",
        "import ",
        "from ",
        "const ",
        "let ",
        "var ",
        "function ",
        "#include",
        "{",
        "};",
        "</",
        "<script",
    )
    if any(marker in lowered for marker in code_markers):
        return False
    words = stripped.split()
    if len(words) < 12:
        return False
    sentence_marks = sum(stripped.count(mark) for mark in ".?!。！？")
    has_article_shape = (
        "\n\n" in stripped
        or ":" in stripped
        or any(line.strip().startswith(("http://", "https://")) for line in stripped.splitlines())
    )
    return sentence_marks >= 1 or has_article_shape


def _caption_text(text: str) -> str:
    normalized = " ".join(text.split()).replace("\\_", "_")
    lowered = normalized.lower()
    markers = ("image caption,", "image caption:", "image caption ")
    marker_positions = [(lowered.rfind(marker), marker) for marker in markers]
    position, marker = max(marker_positions, key=lambda item: item[0])
    if position > 0:
        normalized = normalized[position + len(marker) :].strip(" :,")
    prefixes = (
        "__MERCURY_IMAGE_CAPTION__",
        "Caption:",
        "Caption,",
        "Image caption:",
        "Image caption,",
        "Image caption",
    )
    for prefix in prefixes:
        if normalized.lower().startswith(prefix.lower()):
            return _caption_text(normalized[len(prefix) :].strip(" :,")) or normalized[len(prefix) :].strip(" :,")
    return ""


def _is_caption_label(text: str) -> bool:
    normalized = " ".join(text.split()).strip(" ,:").lower()
    return normalized in {"image caption", "caption"}


def _is_noise_text(text: str) -> bool:
    normalized = " ".join(text.split()).strip()
    lowered = normalized.lower()
    compact = "".join(character for character in lowered if character.isalnum())
    return (
        lowered.startswith(("image source", "source,"))
        or compact.startswith("bypublished")
        or compact.startswith("published")
        or compact.startswith("updated")
        or compact.startswith("byasha")
        or (compact.startswith("by") and len(compact) <= 80)
    )


def _text_key(text: str) -> str:
    return "".join(character.lower() for character in text if character.isalnum())


def _remove_direct_text(tag: object) -> None:
    for child in list(getattr(tag, "contents", [])):
        if isinstance(child, NavigableString):
            child.extract()


def _is_duplicate_heading(text: str, title_key: str, title_words: list[str]) -> bool:
    heading_key = _text_key(text)
    if not title_key or not heading_key:
        return False
    if heading_key == title_key:
        return True
    shared = set(_word_keys(text)) & set(title_words)
    heading_words = set(_word_keys(text))
    title_word_set = set(title_words)
    if not heading_words or not title_word_set:
        return False
    return len(shared) >= 4 and len(shared) / len(heading_words) >= 0.75


def _word_keys(text: str) -> list[str]:
    return ["".join(character.lower() for character in word if character.isalnum()) for word in text.split()]
