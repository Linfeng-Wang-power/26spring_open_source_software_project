# Reader 模块接口与功能说明

`reader` 目录实现 Mercury 的 Reader Pipeline，负责把文章网页或已有 HTML 转换成适合本地阅读器展示的安全内容。

核心处理契约：

```text
source_html -> cleaned_html -> canonical_markdown -> reader_html
```

## 模块职责

| 文件 | 职责 |
| --- | --- |
| `fetcher.py` | 使用 `httpx` 抓取文章原始 HTML，支持重定向、超时和 User-Agent。 |
| `readability.py` | 使用 `readability-lxml` 提取正文和标题，并提供标题、正文 fallback。 |
| `sanitizer.py` | 修复相对链接和懒加载图片地址，清理不安全 HTML 标签、属性和协议。 |
| `markdown_converter.py` | 将 cleaned HTML 转换为 canonical Markdown，并清理异常字符。 |
| `html_renderer.py` | 将 Markdown 渲染为带 Reader CSS 的完整 HTML 页面。 |
| `models.py` | 定义 Reader Pipeline 使用的数据传输对象。 |
| `pipeline.py` | 编排完整 Reader Pipeline，并提供 GUI 原型兼容接口。 |
| `__init__.py` | 暴露 `ReaderPipelineService` 作为模块入口。 |

## 数据结构

### `FetchResult`

字段：

- `source_url: str`：用户或文章条目提供的原始 URL。
- `final_url: str`：HTTP 重定向后的最终 URL。
- `html: str`：抓取到的原始 HTML。

### `ReadabilityResult`

字段：

- `title: str`：提取出的文章标题。
- `content_html: str`：正文提取后的 HTML 片段。

### `ReaderDocument`

字段：

- `title: str`：文章标题。
- `source_url: str`：原始 URL。
- `final_url: str`：最终 URL。
- `source_html: str`：原始 HTML。
- `cleaned_html: str`：清洗后的正文 HTML。
- `canonical_markdown: str`：规范化 Markdown。
- `reader_html: str`：最终用于 Reader 展示的完整 HTML。

## 对外入口

### `ReaderPipelineService`

定义在 `pipeline.py`，是 reader 模块的主要对外接口。

#### `fetch_and_process(url, client=None) -> ReaderDocument`

从 URL 抓取网页并执行完整 Reader Pipeline。

处理流程：

```text
url -> fetch source_html -> extract readable html -> sanitize -> markdown -> reader_html
```

适用场景：

- Feed entry 只有链接，没有全文内容。
- 需要从网页重新生成 Reader 内容。

#### `process_source_html(source_html, source_url, final_url=None) -> ReaderDocument`

直接处理已有 HTML，不执行网络请求。

适用场景：

- Feed 已提供全文 HTML。
- 单元测试 Reader Pipeline。
- 从缓存或 `ContentStore` 读取 source HTML 后重建 Reader 内容。

#### `render_article_html(article) -> str`

兼容当前 `mercury_gui.py` 中的 `ReaderPipeline` 协议。

当前行为：

- 优先读取 `article.markdown`，没有时读取 `article.summary`。
- 直接渲染为 Reader HTML。
- 不执行网页抓取、正文提取或持久化。

#### `clean_current_article(article) -> str`

兼容当前 GUI 原型中的“清洗文章”动作。

当前行为：

- 如果 `article.source_html` 存在，则直接处理已有 HTML。
- 如果没有 `source_html` 但有 `article.url`，则抓取网页并处理。
- 返回清洗结果摘要，包括 cleaned HTML 和 canonical Markdown 长度。

## 已实现功能

1. 抓取文章 HTML。
2. 跟随 HTTP redirect，并记录 final URL。
3. 设置请求 User-Agent 和 timeout。
4. 使用 readability 提取文章正文。
5. 标题提取 fallback：`readability title -> og:title -> twitter:title -> h1 -> title -> Untitled`。
6. 正文提取 fallback：当 readability 输出过短时，尝试从 `<article>`、`<main>`、`role=main` 中选择更完整的正文块。
7. 修复 `<a href>` 和 `<img src>` 中的相对 URL。
8. 支持从懒加载图片属性中提升图片地址，例如 `data-src`、`data-original`、`srcset`。
9. 移除 `<script>` 等不安全内容。
10. 移除 `onerror` 等危险属性。
11. 限制 HTML 允许的标签、属性和协议。
12. 将 cleaned HTML 转换为 canonical Markdown。
13. 清理 Markdown 中的零宽字符、替换符、控制字符和多余空行。
14. 将 Markdown 渲染为带 Reader CSS 的完整 HTML。
15. 在 Reader HTML 中显示可点击的“查看原文”链接。
16. 提供当前 GUI 原型可调用的 `render_article_html` 接口。
17. 提供单元测试覆盖核心 Reader Pipeline。

## 当前测试覆盖

测试文件位于 `tests/test_reader_pipeline.py`。

已覆盖：

1. 抓取时跟随 redirect，并记录 final URL。
2. 清洗 HTML 时移除 script 和危险属性。
3. 将相对链接和图片路径修复为绝对 URL。
4. 从懒加载图片属性中提取可用图片 URL。
5. HTML 转 Markdown 时保留链接和图片。
6. Markdown 转换时清理异常字符。
7. 当 readability 标题为 `[no-title]` 时使用 `h1` 作为 fallback。
8. 当 readability 正文过短时使用 `<article>` 作为正文 fallback。
9. Reader HTML 中生成可点击的“查看原文”链接。
10. 完整 Reader Pipeline 可以输出 `ReaderDocument`。

运行 reader 测试：

```powershell
.\.venv\Scripts\python -m pytest tests\test_reader_pipeline.py -q
```

当前验证结果：

```text
9 passed
```

## 与 GUI / Storage 的关系

Reader Pipeline 本身不直接依赖 Qt，也不直接写数据库。

当前 GUI 集成方式：

- GUI 打开文章时，如果已有缓存的 `ReaderDocument`，优先显示缓存内容。
- 如果没有缓存，则通过 `render_article_html(article)` 显示 feed summary / markdown。
- 用户触发清洗动作时，后台 worker 调用 `fetch_and_process()` 或 `process_source_html()`。
- 清洗完成后，GUI 可以通过 feed/storage service 保存 `ReaderDocument`。

注意：

- 网络抓取、正文解析、Markdown 转换不应在 Qt 主线程执行。
- 当前 Reader HTML 更适合配合 `QTextBrowser` MVP 使用。
- 如果后续使用 `QWebEngineView`，需要单独实现导航拦截和打包验证。

## 已修复的测试报告问题

根据 Windows 和 macOS 测试报告，reader 相关修复包括：

1. 修复标题可能识别为 `[no-title]` 的问题。
2. 增强真实网页正文提取，避免 readability 输出过短时只显示摘要。
3. 清理 Markdown 中的异常字符，改善段尾残留字符问题。
4. 规范多余空行，改善段落排版。
5. 在 Reader HTML 中提供可点击的“查看原文”链接。
6. 整理 `clean_current_article()` 返回文案，避免乱码提示。

## 尚未完成的边界

1. Reader CSS 目前仍内置在 `html_renderer.py`，尚未移动到 `resources/styles/reader.css`。
2. 尚未实现独立的 `mercury/gui/reader_view.py`。
3. 尚未实现 `QWebEngineView` 版本的导航拦截。
4. 对复杂动态网页的正文提取仍可能不完整，需要继续补真实网页回归样例。
5. 对失败场景还需要更多测试，例如超时、非 200 响应、空正文和编码异常。

## 后续建议

1. 将 Reader 样式拆到 `resources/styles/reader.css`。
2. 为真实网页补充小型 fixture，避免依赖外网跑单元测试。
3. 和 Storage 模块继续对齐 `ReaderDocument` 的缓存读写契约。
4. 在 GUI 中明确区分“显示 feed 摘要”和“已清洗全文”状态。
5. 为“查看原文”补充 GUI 层外部浏览器打开测试。
