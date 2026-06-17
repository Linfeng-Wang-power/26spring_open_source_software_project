"""Render canonical Markdown into reader-safe HTML."""

from __future__ import annotations

from html import escape

from markdown_it import MarkdownIt

from mercury.reader.sanitizer import sanitize_html


CLEANED_READER_CSS = """
:root {
  color-scheme: light;
}
body {
  font-family: -apple-system, system-ui, "SF Pro Text", "Segoe UI", "Microsoft YaHei", "Helvetica Neue", Helvetica, Arial, sans-serif;
  color: #1a1a1a;
  background: #ffffff;
  margin: 0;
  padding: 28px 34px 48px;
  line-height: 1.6;
  font-size: 17px;
}
.reader,
.reader-shell {
  max-width: 800px;
  margin: 0 auto;
}
h1 {
  margin: 0 0 0.45em;
  font-size: 2.05em;
  line-height: 1.2;
  font-weight: 760;
  letter-spacing: 0;
  color: #151515;
}
.meta {
  margin: 0 0 2em;
  padding: 0.75em 0 0.85em;
  border-top: 1px solid #eeeeee;
  border-bottom: 1px solid #eeeeee;
  color: #555555;
  font-size: 0.86em;
  line-height: 1.45;
  text-align: left;
  word-break: break-all;
}
h2,
h3,
h4,
h5,
h6 {
  line-height: 1.25;
  margin: 1.6em 0 0.6em;
  color: #1a1a1a;
}
h2 {
  font-size: 1.45em;
  font-weight: 720;
  padding-bottom: 0.28em;
  border-bottom: 1px solid #eeeeee;
}
h3 {
  font-size: 1.22em;
  font-weight: 700;
}
h4,
h5,
h6 {
  font-size: 1.06em;
  font-weight: 700;
}
p {
  margin: 0 0 1em;
}
a {
  color: #0a66cc;
  text-decoration: none;
  border-bottom: 1px solid rgba(10, 102, 204, 0.24);
}
a:hover {
  color: #074f9e;
  border-bottom-color: rgba(7, 79, 158, 0.5);
}
img {
  display: block;
  max-width: 100%;
  height: auto;
  margin: 1.15em auto;
  border-radius: 8px;
}
pre {
  overflow-x: auto;
  padding: 12px 14px;
  margin: 0 0 1em;
  background: #f6f6f6;
  border: 0;
  border-radius: 8px;
}
code {
  font-family: "SF Mono", Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
  font-size: 0.92em;
}
p code,
li code {
  background: #f6f6f6;
  border-radius: 4px;
  padding: 0.12em 0.34em;
}
blockquote {
  margin: 1.2em 0;
  padding-left: 1em;
  border-left: 3px solid #dddddd;
  color: #555555;
}
ul,
ol {
  padding-left: 1.6em;
  margin: 0 0 1em;
}
li {
  margin: 0.25em 0;
}
li > p {
  margin: 0.35em 0;
}
table {
  border-collapse: collapse;
  width: 100%;
  margin: 0 0 1em;
  font-size: 0.95em;
}
td,
th {
  border: 1px solid #dddddd;
  padding: 0.55em 0.7em;
  text-align: left;
  vertical-align: top;
}
th {
  font-weight: 700;
}
thead th {
  border-bottom-width: 2px;
}
tbody tr:nth-child(even) {
  background: #f6f6f6;
}
hr {
  border: 0;
  border-top: 1px solid #eeeeee;
  margin: 1.8em 0;
}
"""


PLAIN_READER_CSS = """
body {
  font-family: -apple-system, system-ui, "SF Pro Text", "Segoe UI", "Microsoft YaHei", "Helvetica Neue", Helvetica, Arial, sans-serif;
  color: #1a1a1a;
  background: #ffffff;
  margin: 0;
  padding: 28px 34px 48px;
  line-height: 1.6;
  font-size: 17px;
}
.reader,
.reader-shell {
  max-width: 800px;
  margin: 0 auto;
}
h1 {
  font-size: 2.05em;
  line-height: 1.2;
  margin: 0 0 0.45em;
  font-weight: 760;
  letter-spacing: 0;
}
.meta {
  color: #555555;
  font-size: 0.86em;
  margin: 0 0 2em;
  padding: 0.75em 0 0.85em;
  border-top: 1px solid #eeeeee;
  border-bottom: 1px solid #eeeeee;
  word-break: break-all;
}
p {
  margin: 0 0 1em;
}
a {
  color: #0a66cc;
  text-decoration: none;
  border-bottom: 1px solid rgba(10, 102, 204, 0.24);
}
img {
  display: block;
  max-width: 100%;
  height: auto;
  margin: 1.15em auto;
  border-radius: 8px;
}
pre {
  overflow-x: auto;
  padding: 12px 14px;
  background: #f6f6f6;
  border-radius: 8px;
}
blockquote {
  margin-left: 0;
  padding-left: 1em;
  border-left: 3px solid #dddddd;
  color: #555555;
}
table {
  border-collapse: collapse;
  width: 100%;
  margin: 0 0 1em;
}
td,
th {
  border: 1px solid #dddddd;
  padding: 0.55em 0.7em;
  text-align: left;
  vertical-align: top;
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
    body_html = sanitize_html(markdown_renderer.render(markdown))
    metadata = _render_source_link(source_url)

    return f"""<!doctype html>
<html>
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>{active_css}</style>
  </head>
  <body>
    <article class="reader reader-shell">
      <h1>{escape(title)}</h1>
      {metadata}
      {body_html}
    </article>
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
