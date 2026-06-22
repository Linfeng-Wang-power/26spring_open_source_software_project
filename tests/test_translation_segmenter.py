from __future__ import annotations

from mercury.agent.translation.segmenter import hash_source_text, segment_markdown


def test_segment_markdown_splits_blank_line_blocks() -> None:
    segments = segment_markdown("First paragraph.\n\nSecond paragraph.")

    assert [s.source_text for s in segments] == [
        "First paragraph.",
        "Second paragraph.",
    ]
    assert [s.position for s in segments] == [0, 1]


def test_segment_markdown_keeps_lists_and_code_blocks() -> None:
    markdown = """# Title

- one
- two

```python
print("hello")

print("again")
```
"""
    segments = segment_markdown(markdown)

    assert segments[0].source_text == "# Title"
    assert segments[1].source_text == "- one\n- two"
    assert "print(\"again\")" in segments[2].source_text
    assert segments[2].source_text.startswith("```python")


def test_segment_markdown_ignores_empty_input() -> None:
    assert segment_markdown(" \n\n\t") == []


def test_source_hash_is_stable_for_trailing_whitespace() -> None:
    assert hash_source_text("hello\nworld") == hash_source_text("hello  \nworld\n")
