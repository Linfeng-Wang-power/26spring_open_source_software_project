# Mercury PyQt Edition - INIT.md

## 1. Project Goal

Mercury PyQt Edition is a local-first, cross-platform AI RSS reader.

The product should help users subscribe to feeds, read cleaned article content, and use AI agents for summary and translation while keeping data on the user's own device.

In one sentence:

> Build a cross-platform desktop RSS reader that combines local article storage, clean reader mode, and model-neutral AI summary / translation.

## 2. Assignment Scope

This project follows the confirmed course requirements:

1. The Friday report focuses on team split, initial plan, and key technology choices.
2. The implementation should not be a macOS-native-only app.
3. The implementation should not require cloud deployment.
4. The product should be local-first: no registration, no login, and all user data stays local by default.
5. The required feature scope is based on the first four items from the Mercury feature list:
   - Feed / OPML parsing, sync, and content display.
   - Cleaned HTML, cleaned Markdown, and custom reading style.
   - Summary Agent with LLM Provider support.
   - Translation Agent.
6. The required technical constraints are:
   - Good product experience.
   - Local-first data policy.
   - Platform-neutral desktop implementation.
   - Model-neutral LLM support.

## 3. Reference Project: `mercury-main`

`mercury-main` is a mature macOS-native Mercury implementation. It is not directly reusable as the final technical stack because it uses SwiftUI and macOS-native APIs, but it is very valuable as an architecture and product reference.

Key ideas we should reuse:

1. Feature-first architecture:
   - `Feed`
   - `Reader`
   - `Agent`
   - `Usage`
   - `Core/Database`
   - `Core/Tasking`
2. Local-first storage:
   - Feed data, reading state, notes, summaries, translations, tags, and usage events are stored locally.
3. Reader pipeline:
   - Source HTML -> readability cleanup -> canonical Markdown -> rendered reader HTML.
4. Agent architecture:
   - Summary, translation, and tagging share runtime/task infrastructure.
   - Agents use prompt templates instead of hardcoded prompt prose.
   - LLM provider configuration is separated from agent business logic.
5. Testing discipline:
   - Feed parsing, database behavior, reader pipeline, translation segmentation, task lifecycle, provider handling, and localization all have dedicated tests.

What we should not copy directly:

1. SwiftUI / AppKit implementation details.
2. macOS-only share services, keychain assumptions, notarization flow, or sandbox-specific file paths.
3. Swift concurrency patterns, except as high-level lessons about task ownership and cancellation.

## 4. Product Modules and Technical Choices

### 4.1 GUI / Desktop Shell

Recommended stack:

```text
PyQt6 or PySide6 + Qt Widgets / Qt WebEngine
```

Preferred decision:

```text
Use PySide6 by default unless the team explicitly accepts PyQt6 GPL/commercial licensing.
```

Reason:

1. Both PyQt6 and PySide6 expose Qt 6 APIs and can build cross-platform desktop applications.
2. PyQt6 is dual-licensed under GPL v3 and Riverbank commercial license. This is acceptable for a course/open-source project but becomes a constraint if the team wants proprietary distribution.
3. PySide6 is the official Qt for Python binding and is available under LGPL/GPL/commercial licensing, which is usually easier for a local-first desktop app prototype.
4. Qt is mature for desktop UI: split panes, tree views, list views, settings dialogs, keyboard shortcuts, menus, system tray, i18n, and embedded web rendering.

Role in Mercury:

1. Main window and layout.
2. Feed sidebar.
3. Article list.
4. Reader panel.
5. Summary / translation panels.
6. Settings pages.
7. Provider configuration screens.
8. Language switching.

PyQt/PySide risks:

1. `QWebEngineView` packaging is heavier and easier to break than basic widgets.
2. Blocking network or LLM calls in the GUI thread will freeze the app.
3. Qt signal/slot lifetime issues can produce callbacks after objects are deleted.
4. Native look and font rendering differ across Windows, Linux, and macOS.
5. Packaging requires collecting Qt plugins, translations, WebEngine resources, and platform plugins.
6. PyQt6 licensing must be understood before distribution.

### 4.2 Programming Language

Recommended stack:

```text
Python 3.11+ or Python 3.12+
```

Reason:

1. Strong ecosystem for RSS, HTML parsing, Markdown conversion, SQLite, and LLM APIs.
2. Good fit for AI-assisted development and rapid prototyping.
3. Simple module boundaries for an 8-person team.
4. Easy to write tests with `pytest`.

Role in Mercury:

1. Application service layer.
2. Feed sync.
3. Reader pipeline.
4. Local storage.
5. Agent runtime.
6. Provider integration.
7. Packaging scripts.

Risks:

1. Long-running CPU or network work must not run on the GUI thread.
2. Dependency version drift can break packaging.
3. Python apps need careful virtual environment and lockfile management.

### 4.3 Local Storage

Recommended stack:

```text
SQLite + SQLAlchemy 2.x
```

Alternative for early MVP:

```text
sqlite3 from Python standard library
```

Reason:

1. SQLite is a single-file local database and matches the local-first constraint.
2. It needs no server and works on all target platforms.
3. SQLAlchemy gives migrations, typed models, query composition, and cleaner testing boundaries.
4. Mercury needs structured persistence, not just JSON files.

Data to store:

1. Feed subscriptions.
2. Feed entries.
3. Raw source HTML.
4. Cleaned HTML.
5. Canonical Markdown.
6. Rendered HTML cache metadata.
7. Summary results.
8. Translation segments.
9. Provider / model configuration metadata.
10. Usage events.
11. UI preferences.

Risks:

1. SQLite connection/threading policy must be explicit.
2. Background workers should not share unsafe session objects with the GUI.
3. Schema migrations need versioning from the beginning.
4. Large article bodies can bloat the database; cache invalidation policy is needed.

### 4.4 Feed Parsing and Sync

Recommended stack:

```text
feedparser + httpx
```

OPML:

```text
xml.etree.ElementTree
```

Reason:

1. `feedparser` handles RSS and Atom compatibility.
2. `httpx` provides timeouts, redirects, headers, and testable transport.
3. OPML is XML, so Python's standard XML tools are sufficient for MVP.

Role in Mercury:

1. Add feed by URL.
2. Import OPML.
3. Export OPML.
4. Sync feeds.
5. Normalize entries.
6. Deduplicate entries by stable ID or URL.
7. Record sync errors without breaking the whole app.

Risks:

1. Feed URLs redirect or fail TLS.
2. Some feeds contain malformed XML.
3. Entries may not have stable IDs.
4. Full article content may not be present in the feed and requires fetching the article page.
5. Sync must be cancellable and must not freeze the GUI.

### 4.5 Content Fetching and Reader Pipeline

Recommended stack:

```text
httpx + readability-lxml + BeautifulSoup4 + markdownify + bleach
```

Target pipeline:

```text
Feed entry / article URL
  -> source HTML
  -> cleaned HTML
  -> canonical Markdown
  -> reader HTML
```

Reason:

1. `mercury-main` shows that a layered reader pipeline is important.
2. Cleaned HTML should be persisted so the app can rebuild Markdown without refetching.
3. Markdown should be the canonical stored format because it is useful for LLM input, export, notes, and reuse.
4. Reader HTML should be a render/cache layer, not the main source of truth.

Role in Mercury:

1. Fetch source page when feed content is incomplete.
2. Extract article body.
3. Remove scripts, ads, nav, unsafe HTML, and tracking noise.
4. Convert cleaned article content into Markdown.
5. Render Markdown into styled HTML for display.

Risks:

1. Readability extraction is imperfect.
2. Image links, captions, tables, code blocks, and lists can degrade during HTML -> Markdown conversion.
3. Relative URLs need a correct base URL.
4. Sanitization must be strict before displaying HTML in a web view.
5. Renderer changes can invalidate translation segment hashes.

### 4.6 Reader Rendering

Recommended stack:

```text
QWebEngineView for rendered HTML reader
markdown-it-py or mistune for Markdown -> HTML
custom CSS themes
```

Reason:

1. RSS articles can contain images, tables, lists, code, and links.
2. A web view gives better rendering quality than plain text widgets.
3. Markdown -> HTML renderer should be deterministic and test-covered.

Role in Mercury:

1. Display cleaned article content.
2. Support light/dark themes.
3. Support font size and font family settings.
4. Support internal link policy and external browser opening.
5. Provide stable DOM segments for translation rendering.

Risks:

1. `QWebEngineView` has packaging and platform dependencies.
2. External navigation must be controlled so untrusted pages do not navigate the app.
3. Local resource paths and base URLs must be resolved correctly.
4. JavaScript should be disabled unless explicitly needed.

### 4.7 Agent Runtime

Recommended stack:

```text
Shared Agent Runtime + Task Queue + per-agent executors
```

Python implementation options:

```text
QThreadPool / QRunnable for Qt-owned background jobs
asyncio + qasync if the team wants async/await integration
```

Default recommendation:

```text
Start with QThreadPool + explicit worker objects.
Introduce qasync only if async integration becomes clearly valuable.
```

Reason:

1. Summary and translation are long-running tasks.
2. Runtime state must be visible to the UI.
3. Cancellation, retry, and failure messages need a shared contract.
4. `mercury-main` shows the importance of one shared task lifecycle instead of feature-local ad hoc runners.

Role in Mercury:

1. Queue agent runs.
2. Track states: idle, queued, running, streaming, succeeded, failed, cancelled.
3. Store successful outputs.
4. Project user-visible status to Reader panels.
5. Avoid duplicate in-flight work for the same entry/slot.

Risks:

1. Qt widgets must only be touched from the main thread.
2. Streaming token updates must be throttled to avoid UI jank.
3. Cancellation is cooperative; network requests may not stop instantly.
4. Entry switching must not accidentally cancel or overwrite in-flight results.

### 4.8 LLM Provider

Recommended stack:

```text
OpenAI-compatible HTTP client abstraction
```

Implementation:

```text
httpx client + internal LLMProvider interface
```

Reason:

1. The project must be model-neutral.
2. Summary and translation should not know provider-specific HTTP details.
3. Local models and commercial APIs can share the same OpenAI-compatible `chat/completions` style route when possible.

Provider data:

1. Provider display name.
2. Base URL.
3. API key or local dummy key.
4. Model name.
5. Timeout.
6. Streaming support flag.

Security:

1. Store API keys in OS keyring if available.
2. Store only provider metadata in SQLite.
3. Never log API keys.
4. Do not proxy requests through a team server.

Risks:

1. Not all "OpenAI-compatible" providers implement exactly the same behavior.
2. Base URL path handling can cause `404` if the client rewrites paths incorrectly.
3. Streaming responses differ across providers.
4. Timeout and retry policy must be explicit.
5. Costs and token counting may not be available for every provider.

### 4.9 Summary Agent

Recommended stack:

```text
Prompt YAML templates + SummaryExecutor + LLMProvider
```

Reason:

1. Summary is high value and lower UI complexity than translation.
2. Output can be displayed in a separate panel.
3. Prompt wording should live in editable templates, not hardcoded inside executor code.

Role in Mercury:

1. Generate short / medium / detailed summaries.
2. Support target language.
3. Stream result to UI.
4. Persist latest successful result per slot.

Slot key:

```text
entry_id + target_language + detail_level + prompt_version + model_id
```

Risks:

1. Hallucination: prompts must instruct the model not to invent facts.
2. Very long articles need truncation, chunking, or map-reduce later.
3. Failed/cancelled runs should not overwrite good persisted results.

### 4.10 Translation Agent

Recommended stack:

```text
Segment extractor + TranslationExecutor + LLMProvider + bilingual renderer
```

Reason:

1. Translation is required by the assignment.
2. The UI should show original/translated segments clearly.
3. Segment-level persistence allows retry and partial recovery.

Role in Mercury:

1. Extract translatable segments from reader HTML or canonical Markdown.
2. Translate by paragraph/list block.
3. Persist segment translations.
4. Render bilingual view.
5. Support retry for failed segments later.

Slot key:

```text
entry_id + target_language + source_content_hash + segmenter_version
```

Risks:

1. Translation can be expensive and slow for long articles.
2. Model output may not match the expected segment format.
3. Segment hashes change when the reader renderer changes.
4. Entry switching and in-flight translation status can confuse users if not designed carefully.

### 4.11 Localization

Recommended stack:

```text
Qt translation system or JSON-based string catalog for MVP
```

MVP recommendation:

```text
Use JSON string catalogs first; migrate to Qt Linguist if the UI grows.
```

Reason:

1. The UI must support Chinese and English.
2. A simple key-based translation system is enough for the course prototype.

Risks:

1. Hardcoded strings spread quickly.
2. Some Qt control helper texts and dialog strings need explicit localization.
3. Dynamic keys are hard to audit.

### 4.12 Packaging and Deployment

Recommended stack:

```text
PyInstaller first; evaluate Nuitka later
```

Reason:

1. PyInstaller is the fastest route for an MVP desktop package.
2. It supports PyQt/PySide packaging but needs careful plugin/resource collection.
3. Nuitka may produce better binaries later but costs more setup time.

Target platforms:

1. Windows.
2. Linux.
3. macOS as a cross-platform build target, not a macOS-native-only implementation.

Risks:

1. Build per platform; do not assume cross-compilation works.
2. Qt platform plugins can be missing at runtime.
3. WebEngine resources can be missing at runtime.
4. Multiple Qt bindings in one environment can break frozen builds.

## 5. MVP Definition

The MVP is complete when:

1. User can add at least one RSS/Atom feed URL.
2. User can import OPML.
3. App can sync feeds and display entries.
4. User can open an entry in Reader mode.
5. App can produce cleaned HTML and canonical Markdown.
6. User can configure an OpenAI-compatible provider.
7. User can run Summary Agent.
8. User can run Translation Agent.
9. Results are persisted locally.
10. UI supports Chinese/English switching.

## 6. Non-Goals for First Iteration

Do not include these in the first MVP:

1. Cloud sync.
2. Accounts or login.
3. Web deployment.
4. Full tag library management.
5. Multi-entry digest export.
6. Usage comparison dashboards.
7. Plugin marketplace.
8. Perfect content extraction for every website.

## 7. Human Pilot Responsibilities

Following the AI Coding Case Study workflow, human team members must own:

1. Product scope.
2. Architecture boundaries.
3. Technology choice decisions.
4. Data privacy policy.
5. Code review.
6. Test coverage requirements.
7. Acceptance criteria.
8. PyQt/PySide licensing decision.

AI can help with:

1. Scaffolding modules.
2. Writing tests.
3. Drafting prompts.
4. Refactoring.
5. Documentation updates.
6. Explaining unfamiliar APIs.

