# Mercury PyQt Edition - INIT 中文版

## 1. 项目目标

Mercury PyQt Edition 是一个本地优先、跨平台的 AI RSS 阅读器。

它的目标是帮助用户订阅 Feed、阅读清洗后的文章内容，并使用 AI Agent 完成摘要和翻译，同时保证用户数据默认保存在本机。

一句话定位：

> 构建一个跨平台桌面 RSS 阅读器，结合本地文章存储、干净的 Reader 模式，以及模型中立的 AI 摘要和翻译能力。

## 2. 作业范围

本项目遵循目前确认的课程要求：

1. 汇报重点是团队成员分工、初步计划和重点技术选型。
2. 不能做 macOS native 单平台应用。
3. 不能做需要云端部署的 Web 方案。
4. 产品必须本地优先：不注册、不登录，所有用户数据默认保存在本地。
5. 必做功能对应 Mercury feature list 的前四项：
   - Feed / OPML 解析、同步和内容呈现。
   - Cleaned HTML、Cleaned Markdown 和自定义阅读样式。
   - Summary Agent，并支持 LLM Provider。
   - Translation Agent。
6. 必须满足的技术约束：
   - 良好的产品体验。
   - 本地优先的数据策略。
   - 平台中立的桌面实现。
   - 大模型中立。

## 3. 参考项目：`mercury-main`

`mercury-main` 是一个成熟的 macOS native Mercury 实现。因为它使用 SwiftUI 和 macOS 原生 API，所以不能直接作为本项目的最终技术栈，但它非常适合作为架构和产品参考。

我们应该借鉴的内容：

1. 按功能划分的架构：
   - `Feed`
   - `Reader`
   - `Agent`
   - `Usage`
   - `Core/Database`
   - `Core/Tasking`
2. 本地优先存储：
   - Feed 数据、阅读状态、笔记、摘要、翻译、标签和使用量事件都保存在本地。
3. Reader 管线：
   - Source HTML -> Readability 清洗 -> canonical Markdown -> rendered Reader HTML。
4. Agent 架构：
   - Summary、Translation、Tagging 共享运行时和任务基础设施。
   - Agent 使用 prompt template，而不是把 prompt 文案硬编码在执行器里。
   - LLM Provider 配置和 Agent 业务逻辑分离。
5. 测试纪律：
   - Feed 解析、数据库行为、Reader 管线、翻译分段、任务生命周期、Provider 处理和本地化都有专门测试。

我们不应该直接照搬的内容：

1. SwiftUI / AppKit 实现细节。
2. macOS-only 的分享服务、Keychain 假设、公证流程和 sandbox 路径。
3. Swift 并发代码。可以借鉴“任务所有权”和“取消策略”的思想，但不能照搬代码。

## 4. 产品模块与技术选型

### 4.1 GUI / 桌面外壳

推荐技术栈：

```text
PyQt6 或 PySide6 + Qt Widgets / Qt WebEngine
```

推荐决策：

```text
默认使用 PySide6，除非团队明确接受 PyQt6 的 GPL / 商业许可限制。
```

原因：

1. PyQt6 和 PySide6 都暴露 Qt 6 API，都可以构建跨平台桌面应用。
2. PyQt6 是 GPL v3 / Riverbank 商业双许可。课程或开源项目可以接受，但如果未来要闭源分发就会有约束。
3. PySide6 是 Qt 官方 Python 绑定，采用 LGPL / GPL / 商业许可路线，通常更适合作为课程原型和本地桌面应用的默认选择。
4. Qt 桌面生态成熟，支持分栏、树形视图、列表视图、设置窗口、快捷键、菜单、本地化和嵌入式网页渲染。

在 Mercury 中的职责：

1. 主窗口和整体布局。
2. Feed 侧边栏。
3. 文章列表。
4. Reader 阅读面板。
5. 摘要 / 翻译面板。
6. 设置页面。
7. Provider 配置页面。
8. 中英文切换。

PyQt / PySide 可能踩的坑：

1. `QWebEngineView` 打包较重，比普通 widgets 更容易在部署时出问题。
2. 如果在 GUI 线程里执行网络请求、LLM 调用或解析任务，界面会卡死。
3. Qt signal / slot 的对象生命周期需要小心，可能出现对象已销毁但回调仍触发的问题。
4. Windows、Linux、macOS 的字体、DPI 和原生控件表现不完全一致。
5. 打包时必须收集 Qt plugins、translations、WebEngine resources 和 platform plugins。
6. 如果使用 PyQt6，必须提前明确许可证风险。

### 4.2 编程语言

推荐技术栈：

```text
Python 3.11+ 或 Python 3.12+
```

原因：

1. Python 在 RSS、HTML 解析、Markdown 转换、SQLite 和 LLM API 调用方面生态成熟。
2. 适合 AI 辅助开发和快速原型。
3. 适合 8 人团队按模块并行开发。
4. 使用 `pytest` 写测试很方便。

在 Mercury 中的职责：

1. 应用服务层。
2. Feed 同步。
3. Reader 管线。
4. 本地存储。
5. Agent runtime。
6. Provider 集成。
7. 打包脚本。

风险：

1. 长时间运行的 CPU、网络、数据库任务不能放在 GUI 线程。
2. 依赖版本漂移可能破坏打包。
3. Python 桌面应用需要明确虚拟环境和 lockfile 管理。

### 4.3 本地存储

推荐技术栈：

```text
SQLite + SQLAlchemy 2.x
```

MVP 简化方案：

```text
Python 标准库 sqlite3
```

原因：

1. SQLite 是单文件本地数据库，符合本地优先约束。
2. 不需要数据库服务器，Windows / Linux / macOS 都可用。
3. SQLAlchemy 提供模型、查询组合、迁移和更清晰的测试边界。
4. Mercury 需要结构化持久化，不适合只用 JSON 文件。

需要保存的数据：

1. Feed 订阅源。
2. Feed entry。
3. 原始 source HTML。
4. cleaned HTML。
5. canonical Markdown。
6. rendered HTML cache 元数据。
7. Summary 结果。
8. Translation segments。
9. Provider / model 配置元数据。
10. LLM usage events。
11. UI 偏好设置。

风险：

1. SQLite 连接和线程策略必须明确。
2. 后台 worker 不应该和 GUI 共享不安全的 session 对象。
3. schema migration 必须从一开始就有版本号。
4. 大量文章正文可能让数据库膨胀，需要缓存失效策略。

### 4.4 Feed 解析和同步

推荐技术栈：

```text
feedparser + httpx
```

OPML：

```text
xml.etree.ElementTree
```

原因：

1. `feedparser` 可以处理 RSS 和 Atom 兼容性。
2. `httpx` 支持 timeout、redirect、headers，并且测试时方便替换 transport。
3. OPML 本质是 XML，MVP 阶段用 Python 标准 XML 工具足够。

在 Mercury 中的职责：

1. 通过 URL 添加 Feed。
2. 导入 OPML。
3. 导出 OPML。
4. 同步 Feed。
5. 规范化 entry。
6. 通过 stable ID 或 URL 去重。
7. 记录单个 Feed 的同步错误，而不是让整个同步失败。

风险：

1. Feed URL 可能重定向或 TLS 失败。
2. 有些 Feed XML 格式不规范。
3. Entry 不一定有稳定 ID。
4. Feed 中可能只有摘要，没有全文，需要额外抓取文章页面。
5. 同步必须可取消或安全中断，不能卡死 GUI。

### 4.5 内容抓取和 Reader 管线

推荐技术栈：

```text
httpx + readability-lxml + BeautifulSoup4 + markdownify + bleach
```

目标管线：

```text
Feed entry / article URL
  -> source HTML
  -> cleaned HTML
  -> canonical Markdown
  -> reader HTML
```

原因：

1. `mercury-main` 证明分层 Reader 管线非常重要。
2. cleaned HTML 应该被保存，这样 Markdown 转换逻辑变化时不用重新请求网络。
3. Markdown 应该作为 canonical stored format，因为它适合 LLM 输入、导出、笔记和复用。
4. Reader HTML 应该是渲染缓存层，而不是主要数据源。

在 Mercury 中的职责：

1. 当 Feed 内容不完整时抓取原文页面。
2. 提取文章主体。
3. 移除脚本、广告、导航、危险 HTML 和跟踪噪音。
4. 把 cleaned article content 转换为 Markdown。
5. 把 Markdown 渲染成带样式的 HTML 显示。

风险：

1. Readability 提取并不完美。
2. 图片链接、caption、表格、代码块、列表可能在 HTML -> Markdown 转换时退化。
3. 相对 URL 需要正确的 base URL。
4. 在 web view 显示 HTML 前必须严格 sanitize。
5. Renderer 变化可能导致翻译分段 hash 变化。

### 4.6 Reader 渲染

推荐技术栈：

```text
QWebEngineView + markdown-it-py 或 mistune + custom CSS themes
```

低风险 MVP 备选：

```text
QTextBrowser
```

原因：

1. RSS 文章可能包含图片、表格、列表、代码和链接。
2. Web view 的渲染质量通常比纯文本控件更好。
3. Markdown -> HTML renderer 必须确定性强，并有测试覆盖。

职责：

1. 显示清洗后的文章。
2. 支持浅色 / 深色主题。
3. 支持字体大小和字体族设置。
4. 控制内部链接策略和外部浏览器打开策略。
5. 为翻译渲染提供稳定的 DOM segment。

风险：

1. `QWebEngineView` 有额外打包和平台依赖。
2. 外部链接必须受控，不能让不可信网页随意导航应用。
3. 本地资源路径和 base URL 需要正确处理。
4. 除非明确需要，否则 Reader 中应该禁用 JavaScript。

### 4.7 Agent Runtime

推荐技术栈：

```text
Shared Agent Runtime + Task Queue + per-agent executors
```

Python / Qt 实现选项：

```text
QThreadPool / QRunnable
asyncio + qasync
```

默认建议：

```text
先用 QThreadPool + 明确的 worker objects。
只有当 async/await 集成价值明显时，再引入 qasync。
```

原因：

1. Summary 和 Translation 都是长任务。
2. Runtime 状态必须能投射到 UI。
3. 取消、重试、失败消息需要共享契约。
4. `mercury-main` 证明应该有一个共享任务生命周期，而不是每个功能自己写一套 runner。

职责：

1. 排队 Agent runs。
2. 跟踪状态：idle、queued、running、streaming、succeeded、failed、cancelled。
3. 存储成功输出。
4. 向 Reader panel 投射用户可见状态。
5. 避免同一个 entry / slot 重复运行。

风险：

1. Qt widgets 只能在主线程更新。
2. streaming token 更新需要节流，否则 UI 会卡。
3. 取消通常是协作式的，网络请求不一定立即停止。
4. 切换 entry 时不能误取消或覆盖 in-flight 结果。

### 4.8 LLM Provider

推荐技术栈：

```text
OpenAI-compatible HTTP client abstraction
```

实现：

```text
httpx client + internal LLMProvider interface
```

原因：

1. 项目必须大模型中立。
2. Summary 和 Translation 不应该知道某个服务商的 HTTP 细节。
3. 本地模型和商业 API 可以尽量共享 OpenAI-compatible `chat/completions` 风格接口。

Provider 数据：

1. Provider display name。
2. Base URL。
3. API key 或本地 dummy key。
4. Model name。
5. Timeout。
6. Streaming support flag。

安全要求：

1. 尽量用 OS keyring 保存 API key。
2. SQLite 只保存 provider metadata。
3. 永远不要记录 API key 到日志。
4. 不通过团队服务器代理请求。

风险：

1. 并不是所有“OpenAI-compatible”服务都完全一致。
2. Base URL path 处理不当可能导致 `404`。
3. 不同 Provider 的 streaming response 有差异。
4. Timeout 和 retry policy 必须明确。
5. 并不是每个 Provider 都提供 token / cost 统计。

### 4.9 Summary Agent

推荐技术栈：

```text
Prompt YAML templates + SummaryExecutor + LLMProvider
```

原因：

1. Summary 价值高，UI 复杂度低于 Translation。
2. 输出可以显示在独立 panel 中。
3. Prompt 文案应该放在可编辑 template 中，而不是硬编码在 executor 里。

职责：

1. 生成 short / medium / detailed 摘要。
2. 支持 target language。
3. 向 UI streaming 输出。
4. 按 slot 保存最新成功结果。

Slot key：

```text
entry_id + target_language + detail_level + prompt_version + model_id
```

风险：

1. 幻觉：Prompt 必须要求模型不要编造事实。
2. 长文章需要截断、分块或 map-reduce。
3. failed / cancelled run 不能覆盖已有成功结果。

### 4.10 Translation Agent

推荐技术栈：

```text
Segment extractor + TranslationExecutor + LLMProvider + bilingual renderer
```

原因：

1. Translation 是作业必做功能。
2. UI 应该清楚显示原文 / 译文 segment。
3. segment-level persistence 支持重试和部分恢复。

职责：

1. 从 Reader HTML 或 canonical Markdown 提取可翻译 segment。
2. 按段落 / 列表 block 翻译。
3. 保存 segment translations。
4. 渲染双语视图。
5. 后续支持失败 segment 重试。

Slot key：

```text
entry_id + target_language + source_content_hash + segmenter_version
```

风险：

1. 长文章翻译慢且费用高。
2. 模型输出可能不符合期望 segment 格式。
3. Reader renderer 变化会改变 segment hash。
4. entry 切换和 in-flight 翻译状态如果设计不好，会让用户误解。

### 4.11 本地化

推荐技术栈：

```text
Qt translation system 或 MVP 阶段 JSON string catalog
```

MVP 建议：

```text
先用 JSON string catalog；UI 变复杂后再迁移到 Qt Linguist。
```

原因：

1. UI 需要支持中文和英文。
2. 课程原型阶段，简单的 key-based 翻译系统已经足够。

风险：

1. 硬编码字符串容易扩散。
2. 部分 Qt control 的辅助文字和 dialog 文案需要单独本地化。
3. 动态生成 key 不利于审查。

### 4.12 打包和部署

推荐技术栈：

```text
MVP 阶段 PyInstaller；后续评估 Nuitka
```

原因：

1. PyInstaller 是最快的 MVP 桌面打包路径。
2. 它支持 PyQt / PySide，但需要仔细收集 plugin 和 resource。
3. Nuitka 后续可能生成更好的二进制，但配置成本更高。

目标平台：

1. Windows。
2. Linux。
3. macOS：作为跨平台构建目标，而不是 macOS-native-only 实现。

风险：

1. 需要在各目标 OS 上分别构建，不应假设能跨平台交叉编译。
2. Qt platform plugins 缺失会导致运行失败。
3. WebEngine resources 缺失会导致 Reader 无法显示。
4. 同一环境中混用多个 Qt binding 会破坏 frozen build。

## 5. MVP 定义

MVP 完成标准：

1. 用户可以添加至少一个 RSS / Atom feed URL。
2. 用户可以导入 OPML。
3. 应用可以同步 Feed 并显示 entry。
4. 用户可以打开 entry 进入 Reader 模式。
5. 应用可以生成 cleaned HTML 和 canonical Markdown。
6. 用户可以配置 OpenAI-compatible Provider。
7. 用户可以运行 Summary Agent。
8. 用户可以运行 Translation Agent。
9. AI 结果保存在本地。
10. UI 支持中文 / 英文切换。

## 6. 第一轮非目标

第一轮 MVP 不做：

1. Cloud sync。
2. 账号或登录。
3. Web 部署。
4. 完整标签库管理。
5. 多篇文摘导出。
6. Usage comparison dashboards。
7. 插件市场。
8. 对所有网站都做到完美内容提取。

## 7. Human Pilot 职责

按照 AI Coding Case Study 的方法，人类团队成员必须负责：

1. 产品范围。
2. 架构边界。
3. 技术选型决策。
4. 数据隐私策略。
5. Code review。
6. 测试覆盖要求。
7. 验收标准。
8. PyQt / PySide 许可证决策。

AI 可以辅助：

1. 搭建模块脚手架。
2. 编写测试。
3. 起草 prompt。
4. 重构。
5. 更新文档。
6. 解释不熟悉的 API。

