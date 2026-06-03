# Reader 模块接口与功能说明

`reader` 目录实现 Mercury 的 Reader 管线 MVP，目标是把文章的原始网页内容处理成适合本地阅读器展示的安全 HTML。

当前核心契约：

```text
source_html -> cleaned_html -> canonical_markdown -> reader_html
```

## 模块职责

| 文件 | 职责 |
| --- | --- |
| `fetcher.py` | 使用 `httpx` 抓取文章原始 HTML，支持重定向、超时和 User-Agent。 |
| `readability.py` | 使用 `readability-lxml` 从原始 HTML 中提取正文和标题。 |
| `sanitizer.py` | 修复相对链接，清理不安全 HTML 标签、属性和协议。 |
| `markdown_converter.py` | 将 cleaned HTML 转换为 canonical Markdown。 |
| `html_renderer.py` | 将 Markdown 渲染为带 Reader CSS 的完整 HTML 页面。 |
| `models.py` | 定义 Reader 管线中使用的数据传输对象。 |
| `pipeline.py` | 编排完整 Reader 管线，并提供当前 GUI 原型可调用的兼容接口。 |
| `__init__.py` | 暴露 `ReaderPipelineService` 作为模块入口。 |

## 数据结构

### `FetchResult`

定义在 `models.py`。

字段：

- `source_url: str`：用户或文章条目提供的原始 URL。
- `final_url: str`：HTTP 重定向后的最终 URL。
- `html: str`：抓取到的原始 HTML。

### `ReadabilityResult`

定义在 `models.py`。

字段：

- `title: str`：从网页中提取出的文章标题。
- `content_html: str`：正文提取后的 HTML 片段。

### `ReaderDocument`

定义在 `models.py`。

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

定义在 `pipeline.py`，是当前 reader 模块最主要的对外接口。

#### `fetch_and_process(url, client=None) -> ReaderDocument`

从 URL 抓取网页并执行完整 Reader 管线。

适用场景：

- Feed entry 只有链接，没有全文内容。
- 需要从网页重新生成 Reader 内容。

处理流程：

```text
url -> fetch source_html -> extract readable html -> sanitize -> markdown -> reader_html
```

#### `process_source_html(source_html, source_url, final_url=None) -> ReaderDocument`

直接处理已有 HTML，不执行网络请求。

适用场景：

- Feed 已经提供全文 HTML。
- 测试 Reader 管线。
- 后续从 `ContentStore` 读取已保存的 source HTML 后重建 Reader 内容。

#### `render_article_html(article) -> str`

兼容当前 `mercury_gui.py` 中的 `ReaderPipeline` 协议。

当前行为：

- 从 `article.markdown` 或 `article.summary` 获取内容。
- 直接渲染为 Reader HTML。
- 不执行网页抓取、正文提取或持久化。

#### `clean_current_article(article) -> str`

兼容当前 GUI 原型中的“清洗文章”动作。

当前行为：

- 如果 `article` 上有 `source_html` 字段，则执行 Reader 管线并返回清洗结果摘要。
- 如果没有 `source_html`，返回说明文本，提示当前只使用 Markdown 渲染。

## 已实现功能

1. 抓取文章 HTML。
2. 跟随 HTTP redirect，并记录 final URL。
3. 设置请求 User-Agent 和 timeout。
4. 使用 readability 提取文章正文。
5. 提取文章标题。
6. 修复 `<a href>` 和 `<img src>` 中的相对 URL。
7. 移除 `<script>` 等不安全内容。
8. 移除 `onerror` 等危险属性。
9. 限制 HTML 允许的标签、属性和协议。
10. 将 cleaned HTML 转换为 canonical Markdown。
11. 将 Markdown 渲染为带 Reader CSS 的完整 HTML。
12. 提供当前 GUI 原型可调用的 `render_article_html` 接口。
13. 提供单元测试覆盖核心 Reader 管线。

## 当前测试覆盖

测试文件位于 `tests/test_reader_pipeline.py`。

已覆盖：

1. 抓取时跟随 redirect，并记录 final URL。
2. 清洗 HTML 时移除 script 和危险属性。
3. 将相对链接和图片路径修复为绝对 URL。
4. HTML 转 Markdown 时保留链接和图片。
5. 完整 Reader 管线可以输出 `ReaderDocument`。

运行测试：

```powershell
.\.venv\Scripts\python -m pytest
```

## 尚未实现的边界

1. 尚未接入数据库持久化。
2. 尚未保存 `source_html`、`cleaned_html`、`canonical_markdown` 到 `ContentStore`。
3. 尚未接入后台任务系统。
4. 不应在 Qt 主线程中直接执行网络抓取或正文解析。
5. 尚未实现独立的 `mercury/gui/reader_view.py`。
6. Reader CSS 目前内置在 `html_renderer.py`，尚未移动到 `resources/styles/reader.css`。
7. 尚未实现 `QWebEngineView` 的导航拦截；当前 MVP 更适合配合 `QTextBrowser` 使用。

## 后续建议

1. 与存储模块对接 `ReaderDocument`，持久化 source HTML、cleaned HTML 和 canonical Markdown。
2. 将 `fetch_and_process` 放入共享任务运行时，避免阻塞 Qt 主线程。
3. 将 Reader 样式拆到 `resources/styles/reader.css`。
4. 为真实网页失败场景补充测试，包括超时、非 200 响应、空正文和编码异常。
