"""Render canonical Markdown into reader-safe HTML."""

from __future__ import annotations

from html import escape

from markdown_it import MarkdownIt

from reader.sanitizer import sanitize_html


DEFAULT_READER_CSS = """
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif;
  color: #202124;
  background: #ffffff;
  margin: 0;
  padding: 34px 54px 80px 54px;
  line-height: 1.72;
  font-size: 18px;
}
h1 {
  font-size: 34px;
  line-height: 1.18;
  margin: 0 0 18px 0;
  letter-spacing: 0;
}
.meta {
  color: #555;
  font-size: 15px;
  margin-bottom: 28px;
}
a {
  color: #2458a6;
}
img {
  display: block;
  max-width: 100%;
  height: auto;
  margin: 18px 0;
}
pre {
  overflow-x: auto;
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
    css: str = DEFAULT_READER_CSS,
) -> str:
    """Render Markdown to a complete HTML document for QTextBrowser/QWebEngineView."""

    markdown_renderer = MarkdownIt("commonmark", {"html": False}).enable("table")
    body_html = sanitize_html(markdown_renderer.render(markdown))
    metadata = _render_source_link(source_url)

    return f"""<!doctype html>
<html>
  <head>
    <meta charset="utf-8">
    <style>{css}</style>
  </head>
  <body>
    <h1>{escape(title)}</h1>
    {metadata}
    {body_html}
  </body>
</html>
"""


def _render_source_link(source_url: str) -> str:
    if not source_url:
        return ""

    safe_url = escape(source_url, quote=True)
    return (
        '<div class="meta">'
        f'<a href="{safe_url}" rel="noopener noreferrer">查看原文</a>'
        f"<br>{escape(source_url)}"
        "</div>"
    )
