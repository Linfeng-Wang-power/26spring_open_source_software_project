# Mercury 团队分工与技术选型

## 1. 成员分工

| 编号 | 成员 | 模块 | 时间 | 主要交付 |
|---|---|---|---|---|
| 1 | 汪琳丰 | 项目 / 架构 / 文档 / 汇报主线 | 全程 | `INIT`、`AGENTS`、`PLAN`、架构图、汇报主线 |
| 2 | 卢雨凝 | GUI / 体验 | 5.29 - 6.5 | PySide6 GUI 原型、Reader 区、AI 操作入口 |
| 3 | 汪琳丰 | Feed / OPML | 5.29 - 6.5 | RSS / Atom 解析、OPML 导入、FeedService |
| 4 | 陈亦楠 | 本地存储 | 5.29 - 6.5 | SQLite schema、StorageService、本地配置 |
| 5 | 周珠晗 | 内容清洗 | 6.5 - 6.12 | Cleaned HTML、Cleaned Markdown、ReaderPipeline |
| 6 | 陆骏凯 | Summary Agent | 6.5 - 6.12 | 摘要 Prompt、SummaryAgent、摘要 demo |
| 7 | 张睿桐 | Translation / Provider | 6.5 - 6.12 | TranslationAgent、LLMProvider、模型中立接口 |
| 8 | 晏康佳 | 测试 / Review | 全程 | 测试清单、接口检查、bug 记录、风险清单 |
| 9 | 张洳维 | 测试 / Review | 全程 | （mac端）测试清单、接口检查、bug记录 |

## 2. 小组划分

| 小组 | 成员 | 时间 | 任务 |
|---|---|---|---|
| 项目 / 架构 | 汪琳丰 | 全程 | 范围控制、接口设计、技术路线、汇报主线 |
| GUI / 体验 | 卢雨凝 | 5.29 - 6.5 | 完成可运行 GUI 原型 |
| Feed + 本地存储 | 汪琳丰、陈亦楠 | 5.29 - 6.5 | Feed / OPML / SQLite / StorageService |
| AI / Reader 功能 | 周珠晗、陆骏凯、张睿桐 | 6.5 - 6.12 | 内容清洗、摘要、翻译、Provider，可并行 |
| 测试 / 文档 | 晏康佳、张洳维 | 全程 | 测试、Review、风险记录、文档更新 |

## 3. 具体功能技术选型表

| 功能模块 | 具体功能 | 技术选型 | 为什么这样选 | 主要接口 | 负责人 |
|---|---|---|---|---|---|
| GUI / 体验 | 主窗口、三栏布局、工具栏、Reader 区、AI 操作入口 | PySide6 / Qt Widgets | 跨平台、成熟、适合桌面应用；比 macOS native 更符合要求 | `MainWindow`、`FeedSidebar`、`EntryListView`、`ReaderView` | 卢雨凝 |
| GUI / 体验 | 左侧栏收起 / 展开、文章搜索、按钮入口 | PySide6 `QSplitter`、`QToolBar`、`QLineEdit` | 可以快速实现清晰桌面 UI，保留后续扩空间 | `on_toggle_sidebar()`、`on_search_changed()` | 卢雨凝 |
| Feed / OPML | RSS / Atom 解析 | `feedparser` | Python 生态成熟，能兼容多种 RSS / Atom 格式 | `FeedService.list_articles()`、`FeedParser.parse()` | 汪琳丰 |
| Feed / OPML | Feed 网络请求和同步 | `httpx` | 支持 timeout、redirect、headers，测试时方便 mock | `SyncService.refresh_all()` | 汪琳丰 |
| Feed / OPML | OPML 导入 | `xml.etree.ElementTree` | OPML 本质是 XML，用标准库即可，减少依赖 | `OPMLService.import_opml(path)` | 汪琳丰 |
| 本地存储 | 保存 Feed、Entry、Content、AI 结果 | SQLite | 单文件本地数据库，不需要服务器，符合本地优先 | `StorageService`、`FeedStore`、`EntryStore`、`ContentStore` | 陈亦楠 |
| 本地存储 | ORM / 数据访问层 | SQLAlchemy 或 MVP 阶段 `sqlite3` | SQLAlchemy 更适合长期维护；`sqlite3` 可用于快速 MVP | `DatabaseSession`、`Repository` | 陈亦楠 |
| 本地存储 | 本地配置 | SQLite + `QSettings` | 业务配置进 SQLite；轻量 UI 偏好可放 `QSettings` | `SettingsStore` | 陈亦楠 |
| 内容清洗 | 抓取文章原始 HTML | `httpx` | 与 Feed 同步共用网络层，方便设置 timeout 和 mock | `ArticleFetcher.fetch(url)` | 周珠晗 |
| 内容清洗 | 正文提取 | `readability-lxml` | 适合从网页中提取正文，减少广告、导航等噪音 | `ContentCleaner.extract(html)` | 周珠晗 |
| 内容清洗 | HTML 清理和结构修复 | BeautifulSoup4、`bleach` | BeautifulSoup 适合处理 HTML 结构；`bleach` 用于安全清洗 | `ContentCleaner.clean_html()` | 周珠晗 |
| 内容清洗 | Cleaned HTML 转 Markdown | `markdownify` | 将清洗后的 HTML 转成 Markdown，方便 LLM 输入和导出 | `MarkdownConverter.to_markdown()` | 周珠晗 |
| Reader 渲染 | Markdown 渲染为 HTML | `markdown-it-py` 或 `mistune` | 输出稳定 HTML，方便 Reader 显示和测试 | `ReaderPipeline.render_article_html()` | 周珠晗 |
| Reader 渲染 | 阅读区显示 | PySide6 `QTextBrowser`，后续可升级 `QWebEngineView` | `QTextBrowser` 打包风险低；`QWebEngineView` 效果更强但打包复杂 | `ReaderView.setHtml()` | 卢雨凝、周珠晗 |
| Summary Agent | 摘要 Prompt 管理 | YAML Prompt Template + PyYAML | Prompt 不硬编码，便于修改和版本管理 | `PromptStore.load("summary")` | 陆骏凯 |
| Summary Agent | 摘要执行 | `SummaryAgent` + `LLMProvider` | Agent 不直接依赖具体模型，符合模型中立 | `SummaryAgent.summarize(article)` | 陆骏凯 |
| Summary Agent | 摘要结果保存 | SQLite | 保存成功摘要，避免重复请求模型 | `SummaryStore.save_result()` | 陆骏凯、陈亦楠 |
| Translation / Provider | LLM Provider 抽象 | OpenAI-compatible API + `httpx` | 可接商业 API、本地模型或其他兼容服务 | `LLMProvider.chat()` | 张睿桐 |
| Translation / Provider | API Key 管理 | `keyring`，fallback 本地配置 | 避免 API Key 明文进入日志和数据库 | `ProviderStore.save_key()` | 张睿桐 |
| Translation / Provider | 翻译 Prompt | YAML Prompt Template + PyYAML | 翻译策略可调整，避免 prompt 散落在代码里 | `PromptStore.load("translation")` | 张睿桐 |
| Translation / Provider | 段落级翻译 | Segment extractor + TranslationAgent | 按段落翻译便于双语显示和失败重试 | `TranslationAgent.translate(article)` | 张睿桐 |
| Translation / Provider | 翻译结果持久化 | SQLite | 保存 segment translation，避免重复翻译 | `TranslationStore.save_segments()` | 张睿桐、陈亦楠 |
| 测试 / Review | 单元测试 | `pytest` | Python 标准测试生态，适合模块测试 | `tests/` | 晏康佳 张洳维 |
| 测试 / Review | GUI 测试 | `pytest-qt` | 可测试 Qt 窗口、按钮、信号 | `test_gui_smoke.py` | 晏康佳 张洳维|
| 测试 / Review | HTTP mock | `httpx.MockTransport` 或 `respx` | 测试不依赖真实网络 | `test_feed_sync.py` | 晏康佳 张洳维 |
| 文档 / 其他 | 项目文档 | Markdown | 与 AI Coding Case Study 对齐，便于持续更新 | `README.md`、`PLAN.md` | 晏康佳 张洳维 |
| 文档 / 其他 | AI 协作记录 | Markdown + 截图 | 记录 AI 生成、人工判断、Review 和风险 | 阶段总结、汇报材料 | 晏康佳 张洳维 |

## 4. 时间计划

| 时间 | 小组 | 成员 | 任务 | 交付 |
|---|---|---|---|---|
| 现在 - 5.29 | 项目 / 架构 | 汪琳丰 | 明确范围、接口、计划 | `INIT`、`AGENTS`、`PLAN`、接口定义 |
| 5.29 - 6.5 | GUI / 体验 | 卢雨凝 | PySide6 主界面、Reader、AI 操作入口 | 可运行 GUI 原型 |
| 5.29 - 6.5 | Feed + 本地存储 | 汪琳丰、陈亦楠 | RSS / Atom、OPML、SQLite、本地 CRUD | `FeedService`、`StorageService` |
| 6.5 - 6.12 | 内容清洗 | 周珠晗 | Cleaned HTML、Cleaned Markdown、ReaderPipeline | 内容清洗 demo |
| 6.5 - 6.12 | Summary Agent | 陆骏凯 | 摘要 prompt、mock provider、摘要输出 | Summary demo |
| 6.5 - 6.12 | Translation / Provider | 张睿桐 | LLMProvider、翻译 Agent、分段翻译 | Translation demo |
| 6.12 - 6.15 | 集成 | 全组 | GUI 接入真实服务 | MVP demo |
| 全程 | 测试 / 文档 | 晏康佳、张洳维 | 测试清单、接口检查、AI 协作记录 | 风险清单、汇报材料 |

## 5. 计划说明

我们将项目分成几个可以并行推进的小组。

5.29 到 6.5，GUI 小组先完成 PySide6 原型，Feed 和本地存储小组同期完成 RSS / OPML / SQLite 的基础能力。

6.5 到 6.12，内容清洗、Summary Agent、Translation / Provider 三个模块并行开发。它们都可以先基于 GUI 中保留的接口和 sample article 进行测试，不需要等待真实 Feed 全部接入。

测试和文档组贯穿始终，负责接口检查、测试清单、风险记录和 AI Coding 协作记录。

