# Mercury PyQt Edition - PLAN 中文版

本计划遵循 AI Coding Case Study 的工作流：

1. 先写文档。
2. 实现前先冻结架构边界。
3. 用小步、可验证的里程碑推进。
4. 在功能里程碑之间穿插重构里程碑。
5. 把测试和人工验收作为一等交付物。

## Phase 0 - 计划和架构

### 目标

把作业要求和 `mercury-main` 参考项目转化为 Python / Qt 项目的明确契约。

### Task 0.1 - 确认产品范围

内容：

1. 必做功能：
   - Feed / OPML 解析和同步。
   - 内容呈现。
   - Cleaned HTML 和 Markdown。
   - Summary Agent。
   - Translation Agent。
2. 必须满足的约束：
   - 本地优先。
   - 跨平台。
   - 模型中立。
   - 良好的产品体验。
3. 明确排除：
   - macOS-native-only 应用。
   - 云端 Web 部署。
   - 账号系统。
   - 云同步。

受影响文件：

1. `INIT.md`
2. `AGENTS.md`
3. `PLAN.md`

验收：

1. 团队可以在一分钟内解释项目范围。
2. 团队可以解释为什么 SwiftUI macOS native 和 cloud Web 都不符合要求。

### Task 0.2 - 决定 Qt binding

内容：

1. 比较 PyQt6 和 PySide6。
2. 记录许可证差异。
3. 在正式实现前选择最终 GUI binding。

推荐结论：

```text
除非团队明确接受 PyQt6 GPL / 商业许可限制，否则选择 PySide6。
```

受影响文件：

1. `AGENTS.md`
2. 未来的 `pyproject.toml`

验收：

1. 决策已记录。
2. 代码库中不混用 PyQt 和 PySide imports。

### Task 0.3 - 定义模块契约

需要定义接口：

1. `FeedService`
2. `OPMLService`
3. `ContentStore`
4. `ReaderPipeline`
5. `LLMProvider`
6. `SummaryAgent`
7. `TranslationAgent`
8. `TaskQueue`
9. `SettingsStore`

验收：

1. 接口先于实现写入文档。
2. GUI 可以调用 service，而不需要知道具体实现细节。

## Phase 1 - 项目脚手架

### 目标

创建一个可运行的桌面应用骨架，并保持清晰的模块边界。

### Task 1.1 - Python 项目设置

内容：

1. 创建 `pyproject.toml`。
2. 添加依赖：
   - PySide6 或 PyQt6。
   - SQLAlchemy。
   - httpx。
   - feedparser。
   - readability-lxml。
   - BeautifulSoup4。
   - markdownify。
   - bleach。
   - markdown-it-py 或 mistune。
   - PyYAML。
   - keyring。
   - pytest。
   - pytest-qt。
3. 添加 lint / type / test 命令。

受影响文件：

1. `pyproject.toml`
2. `README.md`
3. `mercury/`
4. `tests/`

验收：

1. `python -m mercury.app.main` 可以启动空应用。
2. `pytest` 可以运行至少一个 smoke test。

### Task 1.2 - GUI 外壳

内容：

构建：

1. 主窗口。
2. Feed sidebar placeholder。
3. Entry list placeholder。
4. Reader placeholder。
5. Status bar。
6. Settings 入口。
7. 中文 / 英文 UI 切换。

受影响文件：

1. `mercury/gui/main_window.py`
2. `mercury/gui/feed_sidebar.py`
3. `mercury/gui/entry_list.py`
4. `mercury/gui/reader_view.py`
5. `mercury/core/shared/localization.py`

验收：

1. 应用不依赖网络或数据库即可启动。
2. 语言切换可以更新可见标签。
3. GUI smoke test 可以实例化 main window。

### Task 1.3 - 本地路径和设置

内容：

1. 定义 app data directory。
2. 定义 cache directory。
3. 定义 logs directory。
4. 定义 settings store。

受影响文件：

1. `mercury/core/shared/paths.py`
2. `mercury/app/settings.py`

验收：

1. 路径在所有支持 OS 上都能解析。
2. 测试可以覆盖 app data path。

## Phase 2 - 本地存储基础

### 目标

为 Feed、Entry、Content 和 Settings 建立本地持久化。

### Task 2.1 - Database schema v1

表：

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

受影响文件：

1. `mercury/core/database/models.py`
2. `mercury/core/database/session.py`
3. `mercury/core/database/migrations.py`

验收：

1. in-memory database 可以创建 schema。
2. on-disk database 可以打开、关闭、重新打开。
3. migration version 被保存。

### Task 2.2 - Store 层

创建：

1. `FeedStore`
2. `EntryStore`
3. `ContentStore`
4. `AgentRunStore`
5. `ProviderStore`

验收：

1. 每个 store 都有 CRUD 测试。
2. store 模块中不能 import GUI。

## Phase 3 - Feed 和 OPML

### 目标

支持基础内容入口。

### Task 3.1 - Feed 解析

内容：

1. 使用 `httpx` 获取 RSS / Atom。
2. 使用 `feedparser` 解析。
3. 规范化 Feed title、Entry title、URL、published date、author、summary。
4. 对 entry 去重。

受影响文件：

1. `mercury/feed/feed_parser.py`
2. `mercury/feed/feed_service.py`
3. `mercury/feed/sync_service.py`

验收：

1. 能解析 sample RSS fixture。
2. 能解析 sample Atom fixture。
3. malformed feed 产生受控错误。
4. Feed sync 不阻塞 GUI。

### Task 3.2 - OPML 导入

内容：

1. 解析 OPML 文件。
2. 提取 Feed title 和 XML URL。
3. 插入新 Feed。
4. 跳过或合并重复 Feed。

受影响文件：

1. `mercury/feed/opml.py`
2. `mercury/gui/settings_dialog.py` 或导入 action surface。

验收：

1. 能导入 sample OPML。
2. 重复导入是幂等的。
3. 无效 OPML 给出用户可见错误。

### Task 3.3 - GUI 集成

内容：

1. Sidebar 显示 Feed。
2. List 显示 Entry。
3. 添加 Feed action。
4. 导入 OPML action。
5. 刷新 action。

验收：

1. 用户可以添加 Feed URL。
2. 用户可以导入 OPML。
3. 用户可以刷新 Feed。
4. 同步后 entry list 更新。

## Phase 4 - Reader 管线

### 目标

构建内容清洗和 Reader mode 管线。

### Task 4.1 - Source HTML fetcher

内容：

1. 当全文不可用时抓取 article URL。
2. 跟随 redirect。
3. 记录 final URL。
4. 设置 timeout。

受影响文件：

1. `mercury/reader/fetcher.py`

验收：

1. 使用 mocked HTTP 测试 redirect、timeout 和 failure。

### Task 4.2 - Cleaned HTML

内容：

1. 执行 readability extraction。
2. sanitize HTML。
3. 修复相对 URL。
4. 持久化 cleaned HTML。

受影响文件：

1. `mercury/reader/readability.py`
2. `mercury/reader/sanitizer.py`

验收：

1. fixture article 生成稳定 cleaned HTML。
2. scripts 和 unsafe attributes 被移除。
3. 相对图片路径变成绝对路径。

### Task 4.3 - Canonical Markdown

内容：

1. cleaned HTML 转 Markdown。
2. 尽量保留 heading、paragraph、list、link、image、code、blockquote、table。
3. 持久化 canonical Markdown。

受影响文件：

1. `mercury/reader/markdown_converter.py`

验收：

1. HTML -> Markdown fixtures 通过。
2. linked image 不会退化成裸 URL 文本。
3. table 和 list 仍保持有用结构。

### Task 4.4 - Reader 渲染

内容：

1. Markdown 渲染成 HTML。
2. 应用 reader CSS。
3. 在 `QWebEngineView` 或 fallback `QTextBrowser` 中显示。
4. 阻止不安全导航。

受影响文件：

1. `mercury/reader/html_renderer.py`
2. `mercury/gui/reader_view.py`
3. `resources/styles/reader.css`

验收：

1. 打开 entry 后能显示 reader content。
2. theme CSS 生效。
3. 外部链接在应用外打开。

## Phase 5 - Provider 和 Agent Runtime

### 目标

建立模型中立的 LLM 基础设施。

### Task 5.1 - Provider 配置

内容：

1. 添加 provider settings UI。
2. 保存 provider metadata。
3. 如果 keyring 可用，用 keyring 保存 API key。
4. 添加 test connection action。

受影响文件：

1. `mercury/agent/provider/llm_provider.py`
2. `mercury/agent/provider/openai_compatible.py`
3. `mercury/agent/provider/provider_store.py`
4. `mercury/gui/settings_dialog.py`

验收：

1. Provider 可以保存。
2. API key 不出现在日志中。
3. Provider test call 可以 mock。
4. Base URL path 有测试覆盖。

### Task 5.2 - Shared Agent Runtime

内容：

1. 定义 `AgentRun`。
2. 实现 task queue。
3. 实现 state machine。
4. 发出 UI-safe progress signals。
5. 持久化 terminal success metadata。

受影响文件：

1. `mercury/core/tasking/task_queue.py`
2. `mercury/core/tasking/task_state.py`
3. `mercury/agent/runtime/agent_runtime.py`

验收：

1. state transition tests 通过。
2. worker 不直接更新 widget。
3. cancellation 是显式的。

### Task 5.3 - Prompt Templates

内容：

1. 添加 built-in YAML templates。
2. 添加 template renderer。
3. 添加 validation。
4. 添加 override search path。

受影响文件：

1. `mercury/agent/prompts/prompt_store.py`
2. `mercury/agent/prompts/template_renderer.py`
3. `resources/prompts/summary.default.yaml`
4. `resources/prompts/translation.default.yaml`

验收：

1. template render tests 通过。
2. 缺失 required variable 时可预测地失败。
3. executor 在 template render 后不修改 prompt 文案。

## Phase 6 - Summary Agent

### 目标

先实现 UI 复杂度较低的第一个 AI 功能。

### Task 6.1 - Summary Executor

内容：

1. 从 template 构建 summary prompt。
2. 调用 `LLMProvider`。
3. streaming 或返回文本。
4. 按 slot 持久化成功结果。

受影响文件：

1. `mercury/agent/summary/summary_agent.py`
2. `mercury/agent/summary/summary_store.py`

验收：

1. 使用 mocked provider 时 summary 可以运行。
2. failed run 不覆盖已有成功 summary。
3. slot replacement 正常工作。

### Task 6.2 - Summary UI

内容：

1. 在 Reader 中添加 summary panel。
2. 添加 target language selector。
3. 添加 detail level selector。
4. 添加 run、cancel、copy、clear actions。

受影响文件：

1. `mercury/gui/agent_panels.py`
2. `mercury/gui/reader_view.py`

验收：

1. 用户可以运行 summary。
2. 进度可见。
3. 重新选择 entry 后结果仍在。

## Phase 7 - Translation Agent

### 目标

实现 Reader-only translation。

### Task 7.1 - Segment Extraction

内容：

1. 从 rendered reader content 提取稳定 source segments。
2. baseline 支持：paragraph、unordered list、ordered list。
3. 计算 `source_content_hash`。
4. 分配稳定 segment IDs。

受影响文件：

1. `mercury/agent/translation/segmenter.py`

验收：

1. 相同内容生成相同 hash。
2. renderer 变化可以通过 hash 变化检测。
3. unsupported blocks 被安全跳过。

### Task 7.2 - Translation Executor

内容：

1. 翻译 segments。
2. 保持顺序。
3. 持久化成功 segments。
4. 受控处理 partial failure。

受影响文件：

1. `mercury/agent/translation/translation_agent.py`
2. `mercury/agent/translation/translation_store.py`

验收：

1. mocked provider 可以翻译 fixture segments。
2. segment count mismatch 被处理。
3. timeout 产生用户可见 failure。

### Task 7.3 - Bilingual Reader UI

内容：

1. 添加 Translate / Original toggle。
2. 渲染原文和译文。
3. entry 切换时重置为 Original。
4. 已存在翻译时复用 persisted translation。

受影响文件：

1. `mercury/gui/reader_view.py`
2. `mercury/gui/agent_panels.py`

验收：

1. 用户可以运行 translation。
2. 用户可以回到 original。
3. entry 切换不会显示 stale generating 状态。

## Phase 8 - 重构和稳定

### 目标

在继续加功能前控制复杂度。

### Task 8.1 - 架构 Review

检查项：

1. GUI 不包含业务逻辑。
2. Agents 共享 runtime。
3. Provider 代码被隔离。
4. Reader pipeline 各层可独立测试。
5. Database stores 没有重复实现。
6. Prompt 文案由 template 管理。

验收：

1. 重构问题被记录或修复。
2. `AGENTS.md` 被更新。

### Task 8.2 - Packaging Spike

内容：

1. 用 PyInstaller 打包基础应用。
2. 分别尝试有 / 无 `QWebEngineView` 的打包。
3. 记录缺失资源。
4. 如果硬件可用，测试 Windows、Linux 和 macOS cross-platform build。

验收：

1. Packaged app 可以启动。
2. Reader view 可用。
3. Feed sync 可用。
4. Summary / Translation settings 可打开。

## Phase 9 - 可选扩展

MVP 稳定后再开始：

1. 标签系统。
2. 批量打标签。
3. 笔记。
4. 文摘导出。
5. Usage statistics。
6. Theme customization。
7. 本地模型帮助文档。
8. 更高级的打包和自动更新。

## 里程碑总结

| 里程碑 | 名称 | 主要交付 |
|---|---|---|
| M0 | Planning | `INIT.md`、`AGENTS.md`、`PLAN.md` |
| M1 | Scaffold | 可运行 Qt app shell |
| M2 | Storage | SQLite schema 和 stores |
| M3 | Feed | RSS / Atom 和 OPML 内容入口 |
| M4 | Reader | Cleaned HTML、Markdown、Reader 渲染 |
| M5 | Provider | 模型中立 Provider 配置 |
| M6 | Summary | 可用 Summary Agent |
| M7 | Translation | 可用 Translation Agent |
| M8 | Stabilization | 重构、测试、打包 spike |

## MVP 验收清单

1. 应用可以本地启动。
2. 不需要登录或云服务。
3. 用户可以添加 / 导入 Feed。
4. 用户可以同步 Feed。
5. 用户可以打开文章。
6. 应用可以显示 cleaned reader content。
7. 应用把 source HTML、cleaned HTML 和 Markdown 保存在本地。
8. 用户可以配置 OpenAI-compatible Provider。
9. Summary Agent 可以使用 mocked 或真实 Provider 工作。
10. Translation Agent 可以使用 mocked 或真实 Provider 工作。
11. AI 输出保存到本地。
12. 中文 / 英文 UI 切换可用。
13. 自动化测试覆盖核心非视觉行为。
14. 打包路径有文档记录。

