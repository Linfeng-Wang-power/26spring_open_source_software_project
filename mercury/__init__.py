"""Lumen / Mercury PyQt edition.

Top-level package for the local-first cross-platform RSS reader. Submodules:

- ``mercury.feed``    : feed parsing and OPML helpers
- ``mercury.storage`` : SQLite-backed feed/entry/content/agent stores
- ``mercury.reader``  : reader pipeline (cleaned HTML, canonical Markdown)
- ``mercury.agent``   : LLM provider, prompt templates, summary agent
- ``mercury.gui``     : PySide6 main window and view glue
- ``mercury.app``     : application entry point
"""
