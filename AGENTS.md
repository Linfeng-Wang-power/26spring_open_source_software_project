# Mercury PyQt Edition - AGENTS.md

This file is the project memory for AI coding agents and human contributors.

It records the current architecture, constraints, and working rules for the cross-platform Python/Qt implementation of Mercury.

## 1. Communication

1. Communicate with users in Chinese.
2. Keep project documentation in Chinese unless a file is clearly meant for code/API reference.
3. Write code comments in English.
4. Use concise comments only when they clarify non-obvious logic.
5. Do not use emojis in code, comments, or project documentation.

## 2. Product Goal

Build a local-first, cross-platform desktop RSS reader with AI summary and translation.

Required product principles:

1. No registration.
2. No login.
3. No cloud deployment.
4. No proactive user-data collection.
5. User data is stored locally by default.
6. Large model integration is provider-neutral.
7. The same codebase should target Windows, Linux, and macOS.

## 3. Reference Project Boundary

`mercury-main` is a reference implementation, not the target stack.

Use it for:

1. Feature decomposition.
2. Reader pipeline design.
3. Agent runtime design.
4. Prompt-template governance.
5. Testing inspiration.
6. Local-first privacy expectations.

Do not copy:

1. SwiftUI implementation details.
2. macOS-only UI conventions.
3. AppKit-only services.
4. macOS keychain-only assumptions.
5. Swift-specific concurrency code.

## 4. Technology Stack

### 4.1 GUI

Default decision:

```text
PySide6 is preferred for implementation.
PyQt6 is acceptable only if the team explicitly accepts GPL/commercial licensing.
```

Why:

1. PySide6 is the official Qt for Python binding.
2. PyQt6 is mature but GPL/commercial licensed.
3. Both expose Qt 6 and can support cross-platform desktop UI.
4. The project should not depend on macOS-native-only APIs.

Use:

1. `QMainWindow` for the app shell.
2. `QSplitter` for sidebar/list/reader panes.
3. `QTreeView` or `QListView` for feeds.
4. `QTableView` or `QListView` for entries.
5. `QWebEngineView` for Reader rendering if packaging risk is acceptable.
6. `QTextBrowser` as a lower-risk fallback renderer for MVP if WebEngine packaging blocks progress.
7. `QSettings` only for lightweight UI preferences; durable app data belongs in SQLite.

Hard GUI rules:

1. Never block the Qt main thread with network, parsing, database, or LLM work.
2. Never update Qt widgets from worker threads.
3. Use signals to project background results back to the GUI thread.
4. Keep UI text behind localization keys.
5. Keep feature logic out of view classes.

### 4.2 Language and Runtime

Use:

```text
Python 3.11+
```

Rules:

1. Use type hints for public module boundaries.
2. Prefer dataclasses or Pydantic-style models for DTOs.
3. Keep side-effect-heavy services behind explicit interfaces.
4. Do not hide network or database calls inside UI event handlers.

### 4.3 Storage

Use:

```text
SQLite + SQLAlchemy 2.x
```

MVP fallback:

```text
sqlite3 standard library
```

Rules:

1. All persistent user data goes into a user-local app data directory.
2. Keep API keys out of SQLite if OS keyring is available.
3. Schema migrations must be versioned.
4. Use repository/store classes instead of ad hoc SQL in UI code.
5. Tests should default to in-memory SQLite.
6. Use on-disk SQLite tests only for file-locking, migration, or path behavior.

### 4.4 Feed and OPML

Use:

```text
feedparser
httpx
xml.etree.ElementTree
```

Rules:

1. Support RSS and Atom in MVP.
2. OPML import is required.
3. OPML export is desirable but can come after import.
4. Feed sync must be cancellable or safely interruptible.
5. Feed failures should be recorded per feed and must not abort the entire sync.
6. Normalize feed entry identity with stable ID first, canonical URL second.

### 4.5 Reader Pipeline

Use:

```text
readability-lxml
BeautifulSoup4
markdownify
bleach
markdown-it-py or mistune
```

Target contract:

```text
source_html -> cleaned_html -> canonical_markdown -> reader_html
```

Rules:

1. Persist source HTML when available.
2. Persist cleaned HTML.
3. Persist canonical Markdown.
4. Cache rendered reader HTML only as a rebuildable cache.
5. Preserve base URL so relative links/images can be repaired.
6. Sanitize rendered HTML before displaying it.
7. Disable JavaScript in the Reader unless a documented feature requires it.
8. External navigation should open in the system browser, not inside the Reader.

### 4.6 Agent Runtime

Use:

```text
Shared task runtime + per-agent executors
```

Default Qt implementation:

```text
QThreadPool + QRunnable + signals
```

Optional later:

```text
asyncio + qasync
```

Rules:

1. Summary, translation, and future tagging must share task lifecycle infrastructure.
2. Do not build separate ad hoc runners for each agent.
3. Track states explicitly: queued, running, streaming, succeeded, failed, cancelled.
4. User cancellation must be explicit.
5. Do not auto-cancel in-flight work just because the selected entry changes.
6. Entry switching should project persisted state first, then runtime state.
7. Persist only successful payloads unless a failure record is needed for diagnostics.

### 4.7 LLM Provider

Use:

```text
OpenAI-compatible provider abstraction over httpx
```

Rules:

1. Agents must call `LLMProvider`, not provider-specific HTTP code.
2. The provider interface must support:
   - non-streaming chat completion,
   - streaming chat completion if available,
   - timeout,
   - cancellation,
   - provider/model metadata,
   - structured error mapping.
3. Base URL path handling must be tested.
4. Never log API keys.
5. Never send article data to any server except the provider configured by the user.

### 4.8 Prompt Templates

Use:

```text
YAML prompt templates
```

Rules:

1. Built-in templates live under `resources/prompts/`.
2. User overrides live under the app data directory.
3. Executors must not add hidden prompt prose after rendering a template.
4. Reading a template plus render parameters should reconstruct final model-facing messages.
5. Template versions must be recorded with agent outputs.
6. Invalid custom templates should fall back to built-ins with a visible warning.
7. Invalid built-in templates are program bugs and should fail tests.

### 4.9 Packaging

Use:

```text
PyInstaller for MVP packaging
Nuitka evaluation after MVP
```

Rules:

1. Build on each target OS instead of assuming cross-compilation.
2. Keep only one Qt binding in the packaging environment.
3. Test the packaged app, not just `python main.py`.
4. Explicitly verify Qt platform plugins, image plugins, translations, and WebEngine resources.
5. Keep a packaging checklist for Windows, Linux, and macOS.

## 5. Proposed Directory Structure

Use feature-first layout inspired by `mercury-main`, adapted for Python:

```text
mercury/
  app/
    main.py
    app_context.py
    settings.py
  gui/
    main_window.py
    feed_sidebar.py
    entry_list.py
    reader_view.py
    agent_panels.py
    settings_dialog.py
  core/
    database/
      models.py
      migrations.py
      session.py
    tasking/
      task_queue.py
      task_state.py
      worker.py
    shared/
      paths.py
      errors.py
      localization.py
  feed/
    feed_service.py
    feed_parser.py
    opml.py
    sync_service.py
  reader/
    fetcher.py
    readability.py
    markdown_converter.py
    html_renderer.py
    sanitizer.py
    pipeline.py
  agent/
    provider/
      llm_provider.py
      openai_compatible.py
      provider_store.py
    runtime/
      agent_run.py
      agent_runtime.py
    summary/
      summary_agent.py
      summary_store.py
    translation/
      segmenter.py
      translation_agent.py
      translation_store.py
    prompts/
      prompt_store.py
      template_renderer.py
  usage/
    usage_tracker.py
  resources/
    prompts/
    i18n/
    styles/
tests/
```

Rules:

1. Keep files small and named by responsibility.
2. Avoid deep nesting beyond two levels inside a feature unless there is a strong reason.
3. GUI files should only coordinate presentation and call services.
4. Feature services should not import GUI modules.
5. Core utilities must be feature-neutral.

## 6. PyQt/PySide Pitfalls

### 6.1 Licensing

PyQt6 is GPL v3/commercial. If distributed under a non-GPL-compatible license, a commercial PyQt license may be required.

Mitigation:

1. Prefer PySide6 for fewer licensing concerns.
2. If using PyQt6, document that the course prototype is GPL-compatible or not distributed as proprietary software.

### 6.2 GUI Thread Blocking

Network sync, readability parsing, Markdown conversion, database writes, and LLM calls can freeze the app.

Mitigation:

1. Use workers for all long-running work.
2. Send progress and result signals to the GUI thread.
3. Keep UI event handlers short.

### 6.3 Worker Lifetime

Qt objects may be deleted while a worker still holds callbacks.

Mitigation:

1. Use explicit task IDs.
2. Check task ownership before applying UI updates.
3. Disconnect signals or ignore stale task IDs on entry switch.

### 6.4 WebEngine Packaging

`QWebEngineView` depends on extra subprocesses, resources, and platform-specific files.

Mitigation:

1. Use `QTextBrowser` for MVP if packaging blocks progress.
2. Add a dedicated packaging milestone for WebEngine.
3. Test packaged builds on all target platforms.

### 6.5 SQLite Threading

SQLite connections and SQLAlchemy sessions are not automatically safe across arbitrary worker boundaries.

Mitigation:

1. Create sessions per worker/task.
2. Do not share sessions with GUI objects.
3. Use repositories/stores as boundaries.

### 6.6 Signals and Streaming

Streaming LLM token updates can overwhelm the UI.

Mitigation:

1. Buffer tokens in the worker.
2. Emit updates at a controlled interval.
3. Finalize with one terminal signal.

### 6.7 Cross-Platform UI Differences

Fonts, DPI, file dialogs, keyboard shortcuts, and web rendering vary.

Mitigation:

1. Define minimum supported OS versions.
2. Use Qt layout managers, not absolute positioning.
3. Verify with screenshots on multiple platforms.

## 7. Testing Rules

Use:

```text
pytest
pytest-qt
respx or httpx MockTransport
```

Test priorities:

1. Feed parsing.
2. OPML import/export.
3. Reader pipeline layer outputs.
4. Markdown conversion edge cases.
5. Translation segmentation.
6. SQLite persistence and migrations.
7. Provider base URL handling.
8. Prompt template rendering.
9. Agent runtime state transitions.
10. GUI smoke tests for key flows.

Hard rules:

1. Avoid sleep-based tests.
2. Prefer deterministic fake transports and sample fixtures.
3. Never call real LLM APIs in automated tests.
4. Never require network access for unit tests.
5. Keep fixtures small and explicit.

## 8. Known Decisions

1. Local-first is mandatory.
2. Cross-platform desktop is mandatory.
3. Cloud deployment is out of scope.
4. macOS-native-only implementation is out of scope.
5. AI provider neutrality is mandatory.
6. PySide6 is preferred over PyQt6 unless the team decides otherwise.
7. Reader content should use Markdown as the canonical stored representation.
8. Summary and translation should share an agent runtime.
9. Prompt content should be template-owned.

## 9. Open Questions

1. Should the final binding be PySide6 or PyQt6?
2. Should MVP Reader use `QWebEngineView` immediately or start with `QTextBrowser`?
3. Should the first database layer use SQLAlchemy or direct `sqlite3`?
4. Which target OS should be used for the first packaged demo?
5. Which OpenAI-compatible provider should be used for manual demo?
6. Should local model support be included in MVP or documented as supported-by-interface only?

