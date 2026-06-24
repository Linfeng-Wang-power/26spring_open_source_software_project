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


def test_pipeline_prefers_bbc_article_body_over_partial_readability_output() -> None:
    document = ReaderPipelineService().process_source_html(
        """
        <!doctype html>
        <html>
          <head>
            <title>Families call for justice</title>
            <meta property="og:site_name" content="BBC News">
            <meta property="og:url" content="https://www.bbc.com/news/articles/example">
          </head>
          <body>
            <nav><p>BBC News navigation should not appear.</p></nav>
            <main>
              <article>
                <h1>Families call for justice</h1>
                <section data-component="text-block">
                  <p>The review is expected to detail how failings led to deaths and avoidable harm.</p>
                </section>
                <section data-component="text-block">
                  <p>Gary and Sarah Andrews's daughter Wynter died in 2019 just 23 minutes after being born.</p>
                </section>
                <section data-component="text-block">
                  <p>NUH was <a href="/news/uk-england-nottinghamshire-64422598">fined in January 2023</a> after admitting failures in the family's care.</p>
                </section>
                <section data-component="text-block">
                  <p>Gary said the report needed to serve as a wake-up call to the NHS locally and nationally.</p>
                </section>
                <section data-component="text-block">
                  <p>Sarah said families should not have to fight to be heard, believed, and treated with accountability.</p>
                </section>
                <aside>
                  <p>More on this story: a related link should not be used as article body.</p>
                  <a href="/news/related-story">A related story with a working link</a>
                </aside>
              </article>
            </main>
            <footer><p>Follow BBC on social media.</p></footer>
          </body>
        </html>
        """,
        source_url="https://www.bbc.com/news/articles/example?at_medium=RSS",
    )

    assert "Gary and Sarah Andrews" in document.canonical_markdown
    assert "wake-up call to the NHS" in document.canonical_markdown
    assert "[fined in January 2023](https://www.bbc.com/news/uk-england-nottinghamshire-64422598)" in (
        document.canonical_markdown
    )
    assert "BBC News navigation" not in document.canonical_markdown
    assert "More on this story" not in document.canonical_markdown
    assert "Related links" not in document.canonical_markdown
    assert "related-story" not in document.canonical_markdown
    assert document.canonical_markdown.count("# Families call for justice") == 0


def test_pipeline_keeps_bbc_images_and_styles_caption_once() -> None:
    document = ReaderPipelineService().process_source_html(
        """
        <!doctype html>
        <html>
          <head>
            <title>Families call for justice</title>
            <meta property="og:site_name" content="BBC News">
          </head>
          <body>
            <main>
              <article>
                <h1>Families call for justice</h1>
                <figure>
                  <picture>
                    <source srcset="/news/image-large.jpg 1024w, /news/image-small.jpg 640w">
                    <img alt="Jack and Sarah Hawkins">
                  </picture>
                  <figcaption>
                    <span>Image source, PA Media</span>
                    <span>Image caption,</span>
                    Jack and Sarah Hawkins are calling for a statutory public inquiry into poor maternity care.
                  </figcaption>
                </figure>
                <p>Jack and Sarah Hawkins are calling for a statutory public inquiry into poor maternity care.</p>
                <p>Image source, PA Media</p>
                <p>By Asha Patel East Midlands</p>
                <p>Published 24 June 2026, 00:03 BST Updated 1 hour ago</p>
                <p>The mother of a baby who died in the womb said the report was absolutely soul-destroying.</p>
                <p>Families affected by maternity failings said the harm was potentially preventable.</p>
                <p>The review is expected to detail failures and call for accountability.</p>
              </article>
            </main>
          </body>
        </html>
        """,
        source_url="https://www.bbc.com/news/articles/example",
    )

    assert "![Jack and Sarah Hawkins](https://www.bbc.com/news/image-large.jpg)" in document.canonical_markdown
    assert document.canonical_markdown.count("Jack and Sarah Hawkins are calling") == 1
    assert 'class="image-caption"' in document.reader_html
    assert "Image caption" not in document.reader_html
    assert "PA Media" not in document.reader_html
    assert "__MERCURY_IMAGE_CAPTION__" not in document.reader_html
    assert "Image source" not in document.canonical_markdown
    assert "Asha Patel" not in document.canonical_markdown
    assert "Published 24 June" not in document.canonical_markdown
    assert 'align="center"' in document.reader_html
    assert 'style="display:block;width:760px;max-width:100%;height:auto;margin:0 auto 6px auto;"' in (
        document.reader_html
    )
    assert "<picture" not in document.cleaned_html
    assert "<source" not in document.cleaned_html


def test_renderer_exposes_clickable_source_link() -> None:
    html = render_markdown_to_reader_html(
        "Body text.",
        title="Title",
        source_url="https://example.test/article",
    )

    assert 'href="https://example.test/article"' in html
    assert 'class="reader-header"' in html
    assert 'class="reader-body"' in html
    assert "查看原文" in html


def test_renderer_styles_comma_image_caption_prefix() -> None:
    html = render_markdown_to_reader_html(
        "![Alt](https://example.test/image.jpg)\n\nImage caption, A quieter image caption.",
        title="Title",
    )

    assert 'class="image-caption"' in html
    assert 'align="center"' in html
    assert "A quieter image caption." in html
    assert "Image caption," not in html


def test_renderer_keeps_image_when_noise_text_shares_paragraph() -> None:
    html = render_markdown_to_reader_html(
        "![Alt](https://example.test/image.jpg)Image source, PA Media\n\n"
        "Image caption,\n\n"
        "A quieter image caption.",
        title="Title",
    )

    assert 'src="https://example.test/image.jpg"' in html
    assert "Image source" not in html
    assert "A quieter image caption." in html


def test_renderer_removes_bbc_noise_and_duplicate_title() -> None:
    html = render_markdown_to_reader_html(
        "# Calls for justice\n\n"
        "![Alt](https://example.test/image.jpg)\n\n"
        "Image source, PA Media\n\n"
        "Image caption,\n\n"
        "A quieter image caption.\n\n"
        "ByAsha PatelEast Midlands\n\n"
        "- Published24 June 2026, 00:03 BST Updated 1 hour ago\n\n"
        "The mother of a baby said the report was absolutely soul-destroying.",
        title="Calls for justice",
    )

    assert html.count("Calls for justice") == 1
    assert "Image source" not in html
    assert "Image caption," not in html
    assert "ByAsha" not in html
    assert "Published24" not in html
    assert 'class="image-caption"' in html
    assert "A quieter image caption." in html
    assert "font-size:20px" in html


def test_renderer_removes_near_duplicate_heading() -> None:
    html = render_markdown_to_reader_html(
        "## Calls for justice ahead of landmark maternity report\n\n"
        "The mother of a baby said the report was absolutely soul-destroying.",
        title="Calls for justice ahead of landmark Nottingham maternity report",
    )

    assert html.count("Calls for justice ahead") == 1


def test_pipeline_uses_picture_source_when_img_has_no_src() -> None:
    document = ReaderPipelineService().process_source_html(
        """
        <!doctype html>
        <html>
          <head>
            <title>Families call for justice</title>
            <meta property="og:site_name" content="BBC News">
          </head>
          <body>
            <main>
              <article>
                <figure>
                  <picture>
                    <source srcset="data:image/gif;base64,AAAA 160w, /news/image-small.jpg 320w, /news/image-large.jpg 1024w">
                    <img alt="">
                  </picture>
                  <figcaption>Image caption, A useful caption for the first image.</figcaption>
                </figure>
                <p>The mother of a baby said the report was absolutely soul-destroying.</p>
                <p>Families affected by maternity failings said the harm was potentially preventable.</p>
                <p>The review is expected to detail failures and call for accountability.</p>
              </article>
            </main>
          </body>
        </html>
        """,
        source_url="https://www.bbc.com/news/articles/example",
    )

    assert "![A useful caption for the first image.](https://www.bbc.com/news/image-large.jpg)" in (
        document.canonical_markdown
    )


def test_pipeline_expands_bbc_image_width_template() -> None:
    document = ReaderPipelineService().process_source_html(
        """
        <!doctype html>
        <html>
          <head>
            <title>Families call for justice</title>
            <meta property="og:site_name" content="BBC News">
          </head>
          <body>
            <main>
              <article>
                <figure>
                  <picture>
                    <source srcset="https://ichef.bbci.co.uk/news/{width}/cpsprodpb/example.jpg.webp 480w, https://ichef.bbci.co.uk/news/{width}/cpsprodpb/example.jpg.webp 976w">
                    <img alt="Jack and Sarah Hawkins">
                  </picture>
                  <figcaption>Image caption, A useful caption for the first image.</figcaption>
                </figure>
                <p>The mother of a baby said the report was absolutely soul-destroying.</p>
                <p>Families affected by maternity failings said the harm was potentially preventable.</p>
                <p>The review is expected to detail failures and call for accountability.</p>
              </article>
            </main>
          </body>
        </html>
        """,
        source_url="https://www.bbc.com/news/articles/example",
    )

    assert "https://ichef.bbci.co.uk/news/976/cpsprodpb/example.jpg.webp" in document.canonical_markdown
    assert "{width}" not in document.canonical_markdown


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
