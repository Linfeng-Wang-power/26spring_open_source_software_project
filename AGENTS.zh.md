# Mercury PyQt Edition - AGENTS 中文版

本文件是 AI Coding Agent 和团队成员的项目记忆。

它记录 Mercury 跨平台 Python / Qt 实现的架构、约束和协作规则。

## 1. 沟通规则

1. 与用户沟通使用中文。
2. 项目文档默认使用中文，除非某个文件明确是代码或 API 参考。
3. 代码注释使用英文。
4. 只在逻辑不明显时添加简短注释。
5. 代码、注释和项目文档中不要使用 emoji。

## 2. 产品目标

构建一个本地优先、跨平台桌面 RSS 阅读器，支持 AI 摘要和翻译。

产品原则：

1. 不注册。
2. 不登录。
3. 不依赖云端部署。
4. 不主动采集用户数据。
5. 用户数据默认保存在本地。
6. 大模型集成必须 provider-neutral。
7. 同一套代码应支持 Windows、Linux 和 macOS。

## 3. 参考项目边界

`mercury-main` 是参考实现，不是目标技术栈。

可以借鉴：

1. 功能拆分。
2. Reader 管线设计。
3. Agent runtime 设计。
4. Prompt template 治理。
5. 测试思路。
6. 本地优先的隐私期望。

不要照搬：

1. SwiftUI 实现细节。
2. macOS-only UI 约定。
3. AppKit-only 服务。
4. macOS Keychain-only 假设。
5. Swift-specific 并发代码。

## 4. 技术栈

### 4.1 GUI

默认决策：

```text
优先使用 PySide6。
只有当团队明确接受 GPL / 商业许可限制时，才使用 PyQt6。
```

原因：

1. PySide6 是 Qt 官方 Python 绑定。
2. PyQt6 成熟，但采用 GPL / 商业许可。
3. 二者都暴露 Qt 6 API，并支持跨平台桌面 UI。
4. 项目不应依赖 macOS-native-only API。

使用方式：

1. `QMainWindow` 作为应用外壳。
2. `QSplitter` 实现 sidebar / list / reader 分栏。
3. `QTreeView` 或 `QListView` 显示 Feed。
4. `QTableView` 或 `QListView` 显示 entry。
5. 如果打包风险可接受，用 `QWebEngineView` 渲染 Reader。
6. 如果 WebEngine 打包阻塞 MVP，用 `QTextBrowser` 作为低风险 fallback。
7. `QSettings` 只用于轻量 UI 偏好；持久业务数据放 SQLite。

GUI 硬规则：

1. 不能在 Qt 主线程执行网络、解析、数据库、LLM 等长任务。
2. 不能从 worker 线程直接更新 Qt widget。
3. 后台结果必须通过 signal 投射回 GUI 线程。
4. UI 文案必须通过 localization key 管理。
5. View class 中不要写业务逻辑。

### 4.2 语言和运行时

使用：

```text
Python 3.11+
```

规则：

1. 公共模块边界使用 type hints。
2. DTO 优先使用 dataclass 或类似 Pydantic 的模型。
3. 有副作用的 service 必须有明确接口。
4. 不要把网络或数据库调用藏在 UI event handler 中。

### 4.3 存储

使用：

```text
SQLite + SQLAlchemy 2.x
```

MVP fallback：

```text
Python 标准库 sqlite3
```

规则：

1. 所有持久用户数据保存到本地 app data 目录。
2. 如果 OS keyring 可用，API key 不放 SQLite。
3. schema migration 必须版本化。
4. 使用 repository / store class，不要在 UI 代码中写零散 SQL。
5. 测试默认使用 in-memory SQLite。
6. 只有测试文件锁、迁移或路径行为时才使用 on-disk SQLite。

### 4.4 Feed 和 OPML

使用：

```text
feedparser
httpx
xml.etree.ElementTree
```

规则：

1. MVP 支持 RSS 和 Atom。
2. OPML import 是必做功能。
3. OPML export 是可取功能，但可以在 import 后完成。
4. Feed sync 必须可取消或安全中断。
5. 单个 Feed 失败不能中断整个同步。
6. Feed entry identity 优先使用 stable ID，其次使用 canonical URL。

### 4.5 Reader 管线

使用：

```text
readability-lxml
BeautifulSoup4
markdownify
bleach
markdown-it-py 或 mistune
```

目标契约：

```text
source_html -> cleaned_html -> canonical_markdown -> reader_html
```

规则：

1. source HTML 可用时要持久化。
2. cleaned HTML 要持久化。
3. canonical Markdown 要持久化。
4. rendered reader HTML 只作为可重建缓存。
5. 保留 base URL，用于修复相对链接和图片。
6. 显示 HTML 前必须 sanitize。
7. Reader 默认禁用 JavaScript，除非有明确功能需要。
8. 外部导航应在系统浏览器打开，而不是在 Reader 中打开。

### 4.6 Agent Runtime

使用：

```text
共享任务运行时 + 每个 Agent 自己的 executor
```

默认 Qt 实现：

```text
QThreadPool + QRunnable + signals
```

后续可选：

```text
asyncio + qasync
```

规则：

1. Summary、Translation 和未来 Tagging 必须共享任务生命周期基础设施。
2. 不要为每个 Agent 单独写一套 ad hoc runner。
3. 显式跟踪状态：queued、running、streaming、succeeded、failed、cancelled。
4. 取消必须来自用户明确动作。
5. 不要因为 selected entry 变化就自动取消 in-flight work。
6. entry 切换时先投射 persisted state，再投射 runtime state。
7. 默认只持久化成功 payload，失败记录只用于 diagnostics。

### 4.7 LLM Provider

使用：

```text
基于 httpx 的 OpenAI-compatible Provider 抽象
```

规则：

1. Agent 只能调用 `LLMProvider`，不能直接写某个 Provider 的 HTTP 逻辑。
2. Provider 接口必须支持：
   - 非 streaming chat completion；
   - streaming chat completion，如果 Provider 支持；
   - timeout；
   - cancellation；
   - provider / model metadata；
   - structured error mapping。
3. Base URL path 处理必须有测试。
4. 永远不要记录 API key。
5. 除了用户自己配置的 Provider，不要把文章内容发送到任何服务器。

### 4.8 Prompt Templates

使用：

```text
YAML prompt templates
```

规则：

1. 内置模板放在 `resources/prompts/`。
2. 用户 override 放在 app data 目录。
3. Executor 在模板渲染后不能再追加隐藏 prompt 文案。
4. 只读模板和 render parameters，应能还原最终发送给模型的 messages。
5. Agent 输出必须记录 template version。
6. 无效 custom template 应 fallback 到 built-in，并显示 warning。
7. 无效 built-in template 是程序 bug，应该让测试失败。

### 4.9 打包

使用：

```text
MVP 使用 PyInstaller。
MVP 后评估 Nuitka。
```

规则：

1. 在每个目标 OS 上分别构建，不要假设能交叉编译。
2. 打包环境中只保留一个 Qt binding。
3. 必须测试 packaged app，而不只是测试 `python main.py`。
4. 明确验证 Qt platform plugins、image plugins、translations 和 WebEngine resources。
5. 为 Windows、Linux 和 macOS 维护打包 checklist。

## 5. 建议目录结构

采用 feature-first 布局，参考 `mercury-main`，但适配 Python：

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

规则：

1. 文件要小，按职责命名。
2. 除非有强理由，不要在 feature 内超过两层嵌套。
3. GUI 文件只负责 presentation 和 service 调用。
4. Feature service 不应 import GUI module。
5. Core utility 必须 feature-neutral。

## 6. PyQt / PySide 主要坑点

### 6.1 许可证

PyQt6 是 GPL v3 / commercial。若按非 GPL 兼容方式分发，可能需要商业许可。

规避方式：

1. 优先使用 PySide6。
2. 如果使用 PyQt6，文档中明确课程原型是否接受 GPL。

### 6.2 GUI 线程阻塞

网络同步、Readability 解析、Markdown 转换、数据库写入和 LLM 调用都可能卡死界面。

规避方式：

1. 所有长任务用 worker。
2. 用 signal 回传进度和结果。
3. UI event handler 保持短小。

### 6.3 Worker 生命周期

Qt object 可能已经销毁，但 worker 还持有 callback。

规避方式：

1. 使用明确 task ID。
2. 应用 UI 更新前检查 task ownership。
3. entry 切换时断开信号或忽略 stale task ID。

### 6.4 WebEngine 打包

`QWebEngineView` 依赖额外 subprocess、resources 和平台文件。

规避方式：

1. 如果打包阻塞，MVP 用 `QTextBrowser`。
2. 为 WebEngine 单独设置打包里程碑。
3. 在所有目标平台测试 packaged build。

### 6.5 SQLite 线程

SQLite connection 和 SQLAlchemy session 不能随意跨 worker 共享。

规避方式：

1. 每个 worker / task 创建自己的 session。
2. 不和 GUI object 共享 session。
3. 用 repository / store 作为边界。

### 6.6 Signals 和 Streaming

LLM streaming token 更新可能压垮 UI。

规避方式：

1. 在 worker 中 buffer token。
2. 按固定间隔 emit update。
3. 最后发送一个 terminal signal。

### 6.7 跨平台 UI 差异

字体、DPI、文件对话框、快捷键、Web 渲染在不同系统上会有差异。

规避方式：

1. 明确最低支持 OS。
2. 使用 Qt layout managers，不要绝对定位。
3. 在多平台做截图验证。

## 7. 测试规则

使用：

```text
pytest
pytest-qt
respx 或 httpx MockTransport
```

测试优先级：

1. Feed parsing。
2. OPML import / export。
3. Reader pipeline 各层输出。
4. Markdown conversion 边界情况。
5. Translation segmentation。
6. SQLite persistence 和 migrations。
7. Provider base URL handling。
8. Prompt template rendering。
9. Agent runtime state transitions。
10. GUI smoke tests。

硬规则：

1. 避免 sleep-based tests。
2. 优先使用 deterministic fake transports 和 sample fixtures。
3. 自动化测试不能调用真实 LLM API。
4. 单元测试不能依赖网络。
5. Fixture 要小而明确。

## 8. 已知决策

1. 本地优先是强制要求。
2. 跨平台桌面是强制要求。
3. Cloud deployment 不在范围内。
4. macOS-native-only 不在范围内。
5. 大模型中立是强制要求。
6. 除非团队另行决定，否则 PySide6 优先于 PyQt6。
7. Reader 内容使用 Markdown 作为 canonical stored representation。
8. Summary 和 Translation 共享 Agent runtime。
9. Prompt 内容由 template 管理。

## 9. 未决问题

1. 最终选择 PySide6 还是 PyQt6？
2. MVP Reader 是直接用 `QWebEngineView`，还是先用 `QTextBrowser`？
3. 数据库层第一版用 SQLAlchemy 还是直接 `sqlite3`？
4. 第一个 packaged demo 以哪个 OS 为主？
5. 手动 demo 使用哪个 OpenAI-compatible provider？
6. 本地模型支持是否进入 MVP，还是先只保留接口支持？

