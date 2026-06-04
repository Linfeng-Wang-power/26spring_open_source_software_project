from __future__ import annotations

import httpx

from reader.fetcher import SourceHtmlFetcher
from reader.html_renderer import render_markdown_to_reader_html
from reader.markdown_converter import html_to_markdown
from reader.pipeline import ReaderPipelineService
from reader.readability import extract_readable_html
from reader.sanitizer import clean_reader_html


ARTICLE_HTML = """
<!doctype html>
<html>
  <head><title>Mercury Reader Test</title></head>
  <body>
    <header>Navigation</header>
    <article>
      <h1>Mercury Reader Test</h1>
      <p>Reader mode keeps the useful paragraph.</p>
      <p><a href="/about">About Mercury</a></p>
      <img src="images/cover.png" onerror="alert(1)">
      <script>alert("unsafe")</script>
    </article>
  </body>
</html>
"""


def test_fetcher_follows_redirect_and_records_final_url() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == "https://example.test/start":
            return httpx.Response(302, headers={"Location": "/article"})
        return httpx.Response(200, text=ARTICLE_HTML, request=request)

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport, follow_redirects=True) as client:
        result = SourceHtmlFetcher().fetch("https://example.test/start", client=client)

    assert result.source_url == "https://example.test/start"
    assert result.final_url == "https://example.test/article"
    assert "Reader mode keeps" in result.html


def test_sanitizer_removes_script_and_repairs_relative_urls() -> None:
    cleaned = clean_reader_html(
        '<p><a href="/about">About</a><img src="cover.png" onerror="x"></p><script>x</script>',
        "https://example.test/posts/one",
    )

    assert "script" not in cleaned
    assert "onerror" not in cleaned
    assert 'href="https://example.test/about"' in cleaned
    assert 'src="https://example.test/posts/cover.png"' in cleaned


def test_sanitizer_promotes_lazy_image_urls() -> None:
    cleaned = clean_reader_html(
        '<p><img data-src="/lazy.png"></p>'
        '<p><img srcset="/small.png 320w, /large.png 960w"></p>',
        "https://example.test/posts/one",
    )

    assert 'src="https://example.test/lazy.png"' in cleaned
    assert 'src="https://example.test/small.png"' in cleaned
    assert "data-src" not in cleaned
    assert "srcset" not in cleaned


def test_markdown_converter_preserves_links_and_images() -> None:
    markdown = html_to_markdown(
        '<h2>Title</h2><p><a href="https://example.test">Link</a></p>'
        '<p><img src="https://example.test/a.png" alt="Cover"></p>'
    )

    assert "## Title" in markdown
    assert "[Link](https://example.test)" in markdown
    assert "![Cover](https://example.test/a.png)" in markdown


def test_markdown_converter_cleans_abnormal_characters() -> None:
    markdown = html_to_markdown("<p>First\u200b paragraph\ufffd.</p><p>Second\x07 paragraph.</p>")

    assert "\u200b" not in markdown
    assert "\ufffd" not in markdown
    assert "\x07" not in markdown
    assert "First paragraph." in markdown
    assert "Second paragraph." in markdown


def test_readability_uses_h1_when_readability_title_is_missing() -> None:
    result = extract_readable_html(
        """
        <html>
          <head><title>[no-title]</title></head>
          <body><article><h1>Expected Article Title</h1><p>Body text.</p></article></body>
        </html>
        """
    )

    assert result.title == "Expected Article Title"


def test_readability_falls_back_to_article_when_summary_is_too_short() -> None:
    result = extract_readable_html(
        """
        <html>
          <head><title>Fallback Article</title></head>
          <body>
            <p>Short teaser.</p>
            <article>
              <h1>Fallback Article</h1>
              <p>This is the first substantial paragraph used by the reader fallback.</p>
              <p>This is the second substantial paragraph used by the reader fallback.</p>
              <p>This is the third substantial paragraph used by the reader fallback.</p>
              <p>This is the fourth substantial paragraph used by the reader fallback.</p>
              <p>This is the fifth substantial paragraph used by the reader fallback.</p>
              <p>This is the sixth substantial paragraph used by the reader fallback.</p>
            </article>
          </body>
        </html>
        """
    )

    assert "sixth substantial paragraph" in result.content_html


def test_renderer_exposes_clickable_source_link() -> None:
    html = render_markdown_to_reader_html(
        "Body text.",
        title="Title",
        source_url="https://example.test/article",
    )

    assert 'href="https://example.test/article"' in html
    assert "查看原文" in html


def test_pipeline_builds_reader_document() -> None:
    document = ReaderPipelineService().process_source_html(
        ARTICLE_HTML,
        source_url="https://example.test/posts/one",
    )

    assert document.title == "Mercury Reader Test"
    assert "Reader mode keeps the useful paragraph." in document.cleaned_html
    assert "Reader mode keeps the useful paragraph." in document.canonical_markdown
    assert "<script>" not in document.reader_html
    assert "https://example.test/about" in document.cleaned_html
