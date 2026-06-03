"""Render canonical Markdown into reader-safe HTML."""

from __future__ import annotations

from html import escape

from markdown_it import MarkdownIt

from reader.sanitizer import sanitize_html


CLEANED_READER_CSS = """
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif;
  color: #202124;
  background: #fbfaf7;
  margin: 0;
  padding: 46px 48px 88px 48px;
  line-height: 1.78;
  font-size: 18px;
}
.reader-shell {
  max-width: 780px;
  margin: 0 auto;
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
  max-width: 100%;
  height: auto;
  margin: 26px auto;
  border-radius: 6px;
}
pre {
  overflow-x: auto;
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
  padding: 34px 54px 80px 54px;
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
    css: str | None = None,
    polished: bool = True,
) -> str:
    """Render Markdown to a complete HTML document for QTextBrowser/QWebEngineView."""

    active_css = css or (CLEANED_READER_CSS if polished else PLAIN_READER_CSS)
    markdown_renderer = MarkdownIt("commonmark", {"html": False}).enable("table")
    body_html = sanitize_html(markdown_renderer.render(markdown))
    metadata = f"<div class=\"meta\">{escape(source_url)}</div>" if source_url else ""

    return f"""<!doctype html>
<html>
  <head>
    <meta charset="utf-8">
    <style>{active_css}</style>
  </head>
  <body>
    <main class="reader-shell">
      <h1>{escape(title)}</h1>
      {metadata}
      {body_html}
    </main>
  </body>
</html>
"""
