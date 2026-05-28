# Mercury PyQt Edition - PLAN.md

This plan follows the AI Coding Case Study workflow:

1. Start with documentation.
2. Freeze architecture boundaries before implementation.
3. Build in small verifiable milestones.
4. Put refactoring milestones between feature milestones.
5. Keep tests and manual verification as first-class deliverables.

## Phase 0 - Planning and Architecture

### Goal

Turn the assignment requirements and `mercury-main` reference into a Python/Qt project contract.

### Tasks

#### Task 0.1 - Confirm product scope

Details:

1. Required features:
   - Feed / OPML parsing and sync.
   - Content display.
   - Cleaned HTML and Markdown.
   - Summary Agent.
   - Translation Agent.
2. Required constraints:
   - Local-first.
   - Cross-platform.
   - Model-neutral.
   - Good product experience.
3. Excluded:
   - macOS-native-only app.
   - Cloud Web deployment.
   - Account system.
   - Cloud sync.

Affected files:

1. `INIT.md`
2. `AGENTS.md`
3. `PLAN.md`

Verification:

1. Team can explain the scope in one minute.
2. Team can explain why macOS-native SwiftUI and cloud Web are out of scope.

#### Task 0.2 - Decide Qt binding

Details:

1. Compare PyQt6 and PySide6.
2. Document licensing.
3. Choose final GUI binding before serious implementation.

Recommended result:

```text
PySide6 unless the team explicitly accepts PyQt6 GPL/commercial licensing.
```

Affected files:

1. `AGENTS.md`
2. future `pyproject.toml`

Verification:

1. Decision recorded.
2. No mixed PyQt/PySide imports in the codebase.

#### Task 0.3 - Define module contracts

Details:

Create interfaces for:

1. `FeedService`
2. `OPMLService`
3. `ContentStore`
4. `ReaderPipeline`
5. `LLMProvider`
6. `SummaryAgent`
7. `TranslationAgent`
8. `TaskQueue`
9. `SettingsStore`

Verification:

1. Interfaces are documented before implementation.
2. GUI can call services without knowing implementation details.

## Phase 1 - Project Scaffold

### Goal

Create a runnable desktop app skeleton with clean module boundaries.

### Tasks

#### Task 1.1 - Python project setup

Details:

1. Create `pyproject.toml`.
2. Add dependencies:
   - PySide6 or PyQt6.
   - SQLAlchemy.
   - httpx.
   - feedparser.
   - readability-lxml.
   - BeautifulSoup4.
   - markdownify.
   - bleach.
   - markdown-it-py or mistune.
   - PyYAML.
   - keyring.
   - pytest.
   - pytest-qt.
3. Add lint/type/test commands.

Affected files:

1. `pyproject.toml`
2. `README.md`
3. `mercury/`
4. `tests/`

Verification:

1. `python -m mercury.app.main` launches an empty app.
2. `pytest` runs with at least one smoke test.

#### Task 1.2 - GUI shell

Details:

Build:

1. Main window.
2. Feed sidebar placeholder.
3. Entry list placeholder.
4. Reader placeholder.
5. Status bar.
6. Settings entry point.
7. Chinese/English UI toggle.

Affected files:

1. `mercury/gui/main_window.py`
2. `mercury/gui/feed_sidebar.py`
3. `mercury/gui/entry_list.py`
4. `mercury/gui/reader_view.py`
5. `mercury/core/shared/localization.py`

Verification:

1. App launches without network or database.
2. Language switch updates visible labels.
3. GUI smoke test can instantiate main window.

#### Task 1.3 - Local app paths and settings

Details:

1. Define app data directory.
2. Define cache directory.
3. Define logs directory.
4. Define settings store.

Affected files:

1. `mercury/core/shared/paths.py`
2. `mercury/app/settings.py`

Verification:

1. Paths resolve on all supported OSes.
2. Tests can override app data path.

## Phase 2 - Local Storage Foundation

### Goal

Create durable local persistence for feeds, entries, content, and settings.

### Tasks

#### Task 2.1 - Database schema v1

Details:

Tables:

1. `feeds`
2. `entries`
3. `contents`
4. `agent_runs`
5. `summary_results`
6. `translation_results`
7. `translation_segments`
8. `provider_profiles`
9. `model_profiles`
10. `usage_events`

Affected files:

1. `mercury/core/database/models.py`
2. `mercury/core/database/session.py`
3. `mercury/core/database/migrations.py`

Verification:

1. In-memory database can create schema.
2. On-disk database can open, close, and reopen.
3. Migration version is stored.

#### Task 2.2 - Store layer

Details:

Create:

1. `FeedStore`
2. `EntryStore`
3. `ContentStore`
4. `AgentRunStore`
5. `ProviderStore`

Verification:

1. CRUD tests for each store.
2. No GUI import inside store modules.

## Phase 3 - Feed and OPML

### Goal

Support basic content ingestion.

### Tasks

#### Task 3.1 - Feed parsing

Details:

1. Fetch RSS/Atom via `httpx`.
2. Parse via `feedparser`.
3. Normalize feed title, entry title, URL, published date, author, summary.
4. Deduplicate entries.

Affected files:

1. `mercury/feed/feed_parser.py`
2. `mercury/feed/feed_service.py`
3. `mercury/feed/sync_service.py`

Verification:

1. Parse sample RSS fixture.
2. Parse sample Atom fixture.
3. Malformed feed produces controlled error.
4. Feed sync does not block GUI.

#### Task 3.2 - OPML import

Details:

1. Parse OPML file.
2. Extract feed title and XML URL.
3. Insert new feeds.
4. Skip or merge duplicates.

Affected files:

1. `mercury/feed/opml.py`
2. `mercury/gui/settings_dialog.py` or import action surface.

Verification:

1. Import sample OPML.
2. Duplicate import is idempotent.
3. Invalid OPML gives user-visible error.

#### Task 3.3 - GUI integration

Details:

1. Display feeds in sidebar.
2. Display entries in list.
3. Add feed action.
4. Import OPML action.
5. Refresh action.

Verification:

1. User can add a feed URL.
2. User can import OPML.
3. User can refresh feeds.
4. Entry list updates after sync.

## Phase 4 - Reader Pipeline

### Goal

Build the content-cleaning and reader-mode pipeline.

### Tasks

#### Task 4.1 - Source HTML fetcher

Details:

1. Fetch article URL when full content is unavailable.
2. Follow redirects.
3. Record final URL.
4. Apply timeout.

Affected files:

1. `mercury/reader/fetcher.py`

Verification:

1. Mocked HTTP tests for redirects, timeout, and failure.

#### Task 4.2 - Cleaned HTML

Details:

1. Run readability extraction.
2. Sanitize HTML.
3. Repair relative URLs.
4. Persist cleaned HTML.

Affected files:

1. `mercury/reader/readability.py`
2. `mercury/reader/sanitizer.py`

Verification:

1. Fixture article produces stable cleaned HTML.
2. Scripts and unsafe attributes are removed.
3. Relative images become absolute.

#### Task 4.3 - Canonical Markdown

Details:

1. Convert cleaned HTML to Markdown.
2. Preserve headings, paragraphs, lists, links, images, code, blockquotes, and tables as much as practical.
3. Persist canonical Markdown.

Affected files:

1. `mercury/reader/markdown_converter.py`

Verification:

1. HTML -> Markdown fixtures pass.
2. Linked image does not collapse into raw URL text.
3. Tables and lists remain structurally useful.

#### Task 4.4 - Reader rendering

Details:

1. Render Markdown to HTML.
2. Apply reader CSS.
3. Display in `QWebEngineView` or fallback `QTextBrowser`.
4. Block unsafe navigation.

Affected files:

1. `mercury/reader/html_renderer.py`
2. `mercury/gui/reader_view.py`
3. `resources/styles/reader.css`

Verification:

1. Open an entry and display reader content.
2. Theme CSS is applied.
3. External links open outside the app.

## Phase 5 - Provider and Agent Runtime

### Goal

Create model-neutral LLM infrastructure.

### Tasks

#### Task 5.1 - Provider configuration

Details:

1. Add provider settings UI.
2. Store provider metadata.
3. Store API key in keyring if available.
4. Add test connection action.

Affected files:

1. `mercury/agent/provider/llm_provider.py`
2. `mercury/agent/provider/openai_compatible.py`
3. `mercury/agent/provider/provider_store.py`
4. `mercury/gui/settings_dialog.py`

Verification:

1. Provider can be saved.
2. API key is not logged.
3. Test provider call can be mocked.
4. Base URL path tests cover compatible providers.

#### Task 5.2 - Shared agent runtime

Details:

1. Define `AgentRun`.
2. Implement task queue.
3. Implement state machine.
4. Emit UI-safe progress signals.
5. Persist terminal success metadata.

Affected files:

1. `mercury/core/tasking/task_queue.py`
2. `mercury/core/tasking/task_state.py`
3. `mercury/agent/runtime/agent_runtime.py`

Verification:

1. State transition tests pass.
2. Worker does not update widgets directly.
3. Cancellation is explicit.

#### Task 5.3 - Prompt templates

Details:

1. Add built-in YAML templates.
2. Add template renderer.
3. Add validation.
4. Add override search path.

Affected files:

1. `mercury/agent/prompts/prompt_store.py`
2. `mercury/agent/prompts/template_renderer.py`
3. `resources/prompts/summary.default.yaml`
4. `resources/prompts/translation.default.yaml`

Verification:

1. Template render tests pass.
2. Missing required variable fails predictably.
3. Executor does not mutate prompt text after rendering.

## Phase 6 - Summary Agent

### Goal

Implement the first AI feature with lower UI complexity.

### Tasks

#### Task 6.1 - Summary executor

Details:

1. Build summary prompt from template.
2. Call `LLMProvider`.
3. Stream or return text.
4. Persist successful result by slot.

Affected files:

1. `mercury/agent/summary/summary_agent.py`
2. `mercury/agent/summary/summary_store.py`

Verification:

1. Summary works with mocked provider.
2. Failed run does not overwrite successful summary.
3. Slot replacement works.

#### Task 6.2 - Summary UI

Details:

1. Add summary panel in Reader.
2. Add target language selector.
3. Add detail level selector.
4. Add run, cancel, copy, clear actions.

Affected files:

1. `mercury/gui/agent_panels.py`
2. `mercury/gui/reader_view.py`

Verification:

1. User can run summary.
2. Progress is visible.
3. Result persists after reselecting entry.

## Phase 7 - Translation Agent

### Goal

Implement Reader-only translation.

### Tasks

#### Task 7.1 - Segment extraction

Details:

1. Extract stable source segments from rendered reader content.
2. Supported baseline: paragraphs, unordered lists, ordered lists.
3. Compute `source_content_hash`.
4. Assign stable segment IDs.

Affected files:

1. `mercury/agent/translation/segmenter.py`

Verification:

1. Same content produces same hash.
2. Renderer changes are detected by hash change.
3. Unsupported blocks are skipped safely.

#### Task 7.2 - Translation executor

Details:

1. Translate segments.
2. Preserve ordering.
3. Persist successful segments.
4. Handle partial failure in a controlled way.

Affected files:

1. `mercury/agent/translation/translation_agent.py`
2. `mercury/agent/translation/translation_store.py`

Verification:

1. Mocked provider translates fixture segments.
2. Segment count mismatch is handled.
3. Timeout produces user-visible failure.

#### Task 7.3 - Bilingual Reader UI

Details:

1. Add Translate / Original toggle.
2. Render original and translated content.
3. Reset to Original on entry switch.
4. Reuse persisted translation when available.

Affected files:

1. `mercury/gui/reader_view.py`
2. `mercury/gui/agent_panels.py`

Verification:

1. User can run translation.
2. User can return to original.
3. Entry switch does not show stale generating state.

## Phase 8 - Refactoring and Stabilization

### Goal

Control complexity before adding optional features.

### Tasks

#### Task 8.1 - Architecture review

Checklist:

1. GUI does not contain business logic.
2. Agents share runtime.
3. Provider code is isolated.
4. Reader pipeline layers are independently testable.
5. Database stores are not duplicated.
6. Prompt text is template-owned.

Verification:

1. Refactoring issues are filed or fixed.
2. `AGENTS.md` is updated.

#### Task 8.2 - Packaging spike

Details:

1. Package basic app with PyInstaller.
2. Package with and without `QWebEngineView`.
3. Document missing resources.
4. Test one Windows build, one Linux build, and one macOS cross-platform build if hardware is available.

Verification:

1. Packaged app launches.
2. Reader view works.
3. Feed sync works.
4. Summary/translation settings open.

## Phase 9 - Optional Extensions

Only start after MVP is stable.

Options:

1. Tag system.
2. Batch tagging.
3. Notes.
4. Digest export.
5. Usage statistics.
6. Theme customization.
7. Local model helper documentation.
8. More advanced packaging and auto-update.

## Milestone Summary

| Milestone | Name | Main Deliverable |
|---|---|---|
| M0 | Planning | `INIT.md`, `AGENTS.md`, `PLAN.md` |
| M1 | Scaffold | Runnable Qt app shell |
| M2 | Storage | SQLite schema and stores |
| M3 | Feed | RSS/Atom and OPML ingestion |
| M4 | Reader | Cleaned HTML, Markdown, rendered reader |
| M5 | Provider | Model-neutral provider config |
| M6 | Summary | Working Summary Agent |
| M7 | Translation | Working Translation Agent |
| M8 | Stabilization | Refactor, tests, packaging spike |

## Acceptance Checklist for MVP

1. App launches locally.
2. No login or cloud service is required.
3. User can add/import feeds.
4. User can sync feeds.
5. User can open an article.
6. App can show cleaned reader content.
7. App stores source HTML, cleaned HTML, and Markdown locally.
8. User can configure an OpenAI-compatible provider.
9. Summary Agent works with a mocked or real provider.
10. Translation Agent works with a mocked or real provider.
11. AI outputs are saved locally.
12. Chinese/English UI switching works.
13. Automated tests cover core non-visual behavior.
14. Packaged build path is documented.

