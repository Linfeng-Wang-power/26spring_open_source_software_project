# Mercury RSS 阅读器基础功能改进说明

本文记录本次针对 RSS 阅读器基础链路的修复和补充，覆盖 Feed 导入、RSS/Atom 解析、SQLite 存储、Reader 清洗和 GUI 接入。

## 1. 原问题

清洗按钮已经连接到 GUI 事件，但点击后没有真实清洗文章，主要原因是：

1. GUI 当前文章对象没有数据库 `entry_id`，清洗结果无法知道应该保存到哪条文章。
2. GUI 当前文章对象没有 `source_html`，`ReaderPipelineService.clean_current_article()` 只能走提示分支。
3. `ReaderPipelineService` 已经实现了 `fetch_and_process(url)`，但 GUI 没有调用它。
4. `ContentStore.save()` 已经能保存 `ReaderDocument`，但 GUI 没有把清洗结果写入 `contents` 表。
5. 打开文章时也没有优先读取已经清洗过的缓存内容。

## 2. 本次改进

### 2.1 Feed / OPML

文件：

- `mercury_feed.py`
- `tests/test_feed_parsing.py`

改进：

1. RSS 解析现在会读取 `<guid>`，写入 `Article.stable_id`。
2. Atom 解析现在会读取 `<id>`，写入 `Article.stable_id`。
3. RSS / Atom 中的相对文章链接会基于 feed URL 修复成绝对 URL。
4. OPML 导入会过滤无效 URL。
5. OPML 导入会去重相同 `xmlUrl`。
6. 新增测试覆盖 RSS stable id、Atom stable id、OPML 去重和无效 URL 过滤。

当前状态：

- 支持 RSS。
- 支持 Atom。
- 支持 OPML 导入。
- 暂未实现 OPML 导出。
- 当前解析器仍是标准库 XML MVP 实现，还不是 `feedparser`。

### 2.2 SQLite 存储

文件：

- `mercury_storage.py`
- `migrations/0006.add-entry-stable-id.sql`
- `tests/test_storage.py`

改进：

1. `entries` 表新增 `stable_id` 字段。
2. 新增 `(feed_id, stable_id)` 索引。
3. 新增 `(feed_id, url)` 索引。
4. `EntryStore.upsert()` 现在优先按 `feed_id + stable_id` 判断同一篇文章。
5. 没有 stable id 时，回退到 `feed_id + url` 判断同一篇文章。
6. `StorageService._to_article()` 会把 `entry_id` 和 `stable_id` 返回给 GUI。
7. `StorageService` 新增：
   - `get_reader_document(entry_id)`
   - `save_reader_document(entry_id, document)`

这样 GUI 可以把列表中的文章对象映射回数据库 entry，并把清洗后的 reader 内容保存到 `contents` 表。

### 2.3 Reader 清洗

文件：

- `reader/pipeline.py`

改进：

1. `clean_current_article()` 不再只返回占位提示。
2. 如果文章已有 `source_html`，会直接处理源 HTML。
3. 如果没有 `source_html` 但有 URL，会调用 `fetch_and_process(url)`：
   - 抓取源 HTML；
   - readability 提取正文；
   - 清洗 HTML；
   - 转换 canonical Markdown；
   - 渲染 reader HTML。

### 2.4 GUI 接入

文件：

- `mercury_gui.py`

改进：

1. `Article` DTO 新增 `stable_id` 和 `entry_id` 字段。
2. 打开文章时，如果数据库已有清洗缓存，会优先显示 `contents.reader_html`。
3. 点击“清洗”时会启动后台 `QThread`，避免网络抓取和 HTML 处理阻塞 Qt 主线程。
4. 后台 worker 完成后，GUI 线程会：
   - 将 `ReaderDocument` 保存到 SQLite；
   - 刷新右侧 Reader 面板；
   - 显示清洗结果统计。
5. 清洗过程中会禁用清洗按钮，避免重复启动任务。

### 2.5 Reader 图片展示

文件：

- `reader/sanitizer.py`
- `mercury_gui.py`
- `tests/test_reader_pipeline.py`

改进：

1. 清洗阶段会把懒加载图片属性提升为标准 `src`：
   - `data-src`
   - `data-original`
   - `data-lazy-src`
   - `data-url`
   - `srcset`
   - `data-srcset`
2. 图片相对 URL 会基于文章 URL 修复为绝对 URL。
3. 清洗完成后会移除不再需要的懒加载属性，只保留安全的 `src`、`alt`、`title`。
4. GUI Reader 面板从普通 `QTextBrowser` 改为 `ReaderTextBrowser`。
5. `ReaderTextBrowser.loadResource()` 会显式加载 http/https 远程图片并缓存为 `QImage`。

这样清洗后的 Reader HTML 中只要保留了图片 URL，右侧阅读区就可以展示远程图片。

### 2.6 订阅和文章状态功能

文件：

- `mercury_storage.py`
- `mercury_gui.py`
- `mercury_feed.py`
- `tests/test_storage.py`

改进：

1. 新增删除订阅功能：
   - GUI 工具栏增加“删除订阅”。
   - 只能删除真实订阅，不能删除 `All Feeds` 和 `Starred` 内置视图。
   - 删除前会二次确认。
   - SQLite 中删除 `feeds` 记录后，`entries`、`contents`、`tags` 会通过外键级联删除。
2. 新增收藏功能：
   - GUI 工具栏增加“收藏 / 取消收藏”。
   - 状态写入 `entries.is_starred`。
   - `Starred` 内置视图会基于数据库状态刷新。
3. 新增已读 / 未读功能：
   - 点击文章后会自动标记为已读。
   - GUI 工具栏保留“标记未读 / 标记已读”作为手动修正入口。
   - 状态写入 `entries.is_unread`。
   - 文章列表会显示“未读 / 已读”。
   - 未读文章标题加粗显示。
4. 新增未读筛选：
   - 文章列表顶部的 `Unread` 按钮从占位改为真实筛选。
   - 筛选会重新查询数据库，而不是只在 UI 层隐藏。
5. 清洗成功后不再弹窗：
   - 成功时只刷新 Reader 面板和底部状态栏。
   - 失败时仍然弹出错误窗口。
6. 新增还原功能：
   - GUI 工具栏增加“还原”。
   - 点击后显示文章未清洗前的摘要 / 原始列表内容。
   - 还原只改变当前 Reader 显示，不删除数据库中的清洗缓存。
7. 收藏交互增强：
   - 文章列表中的星星从静态文本改为可点击按钮。
   - 点击星星即可收藏 / 取消收藏。
   - 工具栏收藏按钮仍保留，作为键盘或菜单式操作入口。

### 2.7 刷新订阅后台化

文件：

- `mercury_gui.py`
- `mercury_storage.py`

改进：

1. 刷新的真实作用：
   - 遍历数据库中的所有订阅源；
   - 重新请求 RSS / Atom XML；
   - 解析新文章；
   - 按 stable id / URL 更新 `entries` 表；
   - 更新未读数和文章列表。
2. 原问题：
   - `refresh_all()` 之前在 Qt 主线程中同步执行；
   - 网络请求慢或某个订阅源超时时会导致 GUI 卡住。
3. 本次修复：
   - 新增 `RefreshFeedsWorker`；
   - 刷新在 `QThread` 中执行；
   - 刷新时禁用刷新按钮；
   - 刷新成功后只更新底部状态栏、左侧 footer 的最近刷新时间并刷新列表；
   - 部分订阅失败时才弹出错误窗口。
4. SQLite 线程安全：
   - `StorageService.create_worker_copy()` 会为 worker 创建同数据库路径的新服务实例；
   - worker 使用自己的 SQLite connection，避免跨线程复用 GUI 线程中的连接。

### 2.8 Tags 真实功能

当前 `tags` 表已经存在，Feed 解析时也会给文章写入基础标签，例如 `RSS` / `Atom`。本次把 Tags 从占位入口改成真实功能：

1. 标签筛选：
   - 左侧 `Tags` 页展示所有标签和文章数量；
   - 点击标签后，文章列表只显示该标签下的文章；
   - 可与未读筛选叠加。
2. 用户自定义标签：
   - 工具栏中添加 / 删除当前文章标签；
   - 标签写入 `tags(entry_id, tag)`；
   - 支持“稍后读”“项目资料”“课程引用”等本地分类。
3. 批量操作：
   - 对某个标签下的文章批量标记已读；
   - 批量收藏；
   - 批量清洗并保存 Reader 缓存。
4. 搜索增强：
   - 搜索时支持 `tag:Python`、`tag:AI` 这样的限定条件。
5. 自动标签：
   - 暂时不实现 AI Agent 自动标签；
   - 后续可以根据文章正文生成建议标签，并让用户确认后再入库。

### 2.9 侧边栏和批量删除

文件：

- `mercury_gui.py`
- `mercury_storage.py`

改进：

1. 点击 `Feeds` / `Tags` tab 不再弹出占位说明框。
2. `Feeds` tab 展示订阅列表。
3. `Tags` tab 展示真实标签列表。
4. 左侧订阅列表支持多选。
5. 左侧真实订阅支持 checkbox 勾选。
6. 点击“批量删除”会删除已勾选的多个真实订阅。
7. 点击“删除订阅”仍可删除当前选中的真实订阅。
8. `All Feeds` 和 `Starred` 内置视图不会被删除。
9. 删除订阅后会刷新左侧列表、文章列表和底部状态。

### 2.10 近期交互和视觉调整

文件：

- `mercury_gui.py`
- `reader/html_renderer.py`

改进：

1. 软件可见名称从 `Mercury` 改为 `Lumen`。
2. 手动点击“标记未读”后，当前文章行会立即显示未读状态。
3. 手动标记未读后的自动已读会跳过一次，避免刚标未读马上被重新打开事件改回已读。
4. 清洗后的 Reader 标题居中显示，字体更醒目。
5. 清洗后标题下方的文章 URL 改为灰色、小字号、居中显示。
6. 侧边栏展开 / 收起不再弹出说明窗口，只在底部状态栏提示。
7. 未清洗文章使用朴素阅读样式。
8. 清洗后的文章使用精致 Reader 样式。
9. 点击“还原”会恢复到未清洗的朴素样式。

### 2.11 数据库订阅清理

本次按用户截图清理了本地 SQLite 数据库订阅。

操作前已备份数据库：

```text
/Users/wangxiaohei/.mercury_pyqt/mercury.before-feed-prune.20260603225843.db
```

删除结果：

```text
删除 184 个订阅
保留 13 个订阅
```

保留订阅：

```text
iDaily · 每日环球视野
- 求是网
新华社新闻_新华网
《联合早报》-中港台-即时
《联合早报》-国际-即时
南方周末-新闻
南方周末-推荐
澎湃新闻 - 首页头条
首页头条--人民网
人民网-国内新闻
人民网-国际新闻
人民网-英语新闻
人民日报
```

## 3. 当前基础功能链路

### 3.1 导入 OPML

1. 用户点击 GUI 工具栏“导入 OPML”。
2. `StorageService.import_opml(path)` 读取 OPML 文件。
3. `parse_opml()` 解析订阅源并过滤无效/重复 URL。
4. 新订阅源写入 `feeds` 表。
5. 用户点击“刷新”后再拉取各 feed 的文章。

### 3.2 添加 / 刷新 Feed

1. `StorageService.add_feed(url)` 或 `StorageService.refresh_all()` 发起 HTTP 请求。
2. `parse_feed_xml()` 解析 RSS 或 Atom。
3. 文章写入 `entries` 表。
4. 同一篇文章优先按 `stable_id` 更新，避免 URL 变化时重复插入。

### 3.3 清洗文章

1. 用户在 GUI 中选择文章。
2. 用户点击“清洗”。
3. `CleanArticleWorker` 在后台线程调用 `ReaderPipelineService.fetch_and_process(article.url)`。
4. 生成 `ReaderDocument`。
5. GUI 线程调用 `StorageService.save_reader_document(article.entry_id, document)`。
6. `contents` 表保存：
   - `source_html`
   - `cleaned_html`
   - `canonical_markdown`
   - `reader_html`
7. Reader 面板显示清洗后的 `reader_html`。
8. Reader 面板遇到远程图片时通过 `ReaderTextBrowser` 加载并显示。
9. 清洗成功不弹窗，只在底部状态栏显示结果。
10. 下次打开同一篇文章时优先读取缓存，不需要重新抓取正文。
11. 用户点击“还原”时，当前 Reader 面板会临时显示清洗前的文章摘要内容。

### 3.4 刷新订阅

1. 用户点击“刷新”。
2. GUI 禁用刷新按钮，并启动 `RefreshFeedsWorker`。
3. worker 创建线程内专用的 `StorageService`。
4. worker 执行 `refresh_all()`：
   - 请求每个 feed；
   - 解析 RSS / Atom；
   - upsert 新文章；
   - 收集单个 feed 的失败信息。
5. worker 完成后回到 GUI 线程。
6. GUI 重新加载订阅列表和文章列表。
7. 如果全部成功，更新底部状态栏和左侧最近刷新时间。
8. 如果部分失败，弹出错误窗口显示失败 feed。

### 3.5 标签功能

1. 用户点击左侧 `Tags`。
2. GUI 查询 `StorageService.list_tags()`。
3. 左侧显示标签和文章数量。
4. 用户点击某个标签。
5. GUI 查询 `StorageService.list_articles_by_tag(tag)`。
6. 文章列表显示该标签下的文章。
7. 用户可以：
   - 给当前文章添加标签；
   - 移除当前文章标签；
   - 批量将该标签下文章标为已读；
   - 批量收藏该标签下文章；
   - 批量清洗该标签下文章。

## 4. 验证结果

已通过：

```text
pytest -q tests/test_feed_parsing.py
3 passed
```

已通过：

```text
python -m py_compile mercury_gui.py mercury_storage.py mercury_feed.py reader/pipeline.py tests/test_feed_parsing.py tests/test_storage.py
```

已通过：

```text
python -m py_compile mercury_gui.py reader/sanitizer.py tests/test_reader_pipeline.py
```

已通过：

```text
python -m py_compile mercury_gui.py mercury_storage.py mercury_feed.py tests/test_storage.py
```

完整测试当前无法在本机环境完成，原因是当前 Python 环境缺少项目依赖：

```text
ModuleNotFoundError: No module named 'markdownify'
ModuleNotFoundError: No module named 'yoyo'
```

这些依赖已经列在 `requirements.txt` 中。安装依赖后建议重新运行：

```text
pip install -r requirements.txt
pytest -q
```

## 5. 仍需后续完善

1. Feed 解析建议从当前标准库 XML MVP 实现升级为 `feedparser`，提高真实世界兼容性。
2. 刷新 Feed 目前仍在 GUI 主线程调用，后续应和清洗一样放入统一任务队列。
3. 清洗任务目前支持后台执行，但还没有统一的 queued/running/succeeded/failed/cancelled 状态模型。
4. OPML 目前只有导入，没有导出。
5. `ContentStore` 已经保存源 HTML 和清洗结果，但还没有 UI 入口展示 Markdown 或原始 HTML。
6. 需要为 GUI 清洗流程补充 `pytest-qt` 或手动 smoke test。
7. 远程图片加载目前使用同步 `loadResource()`，后续可升级为异步图片缓存，避免极慢图片影响 Reader 首次渲染。
8. “还原”目前只还原当前显示，不清除缓存；后续可增加“删除清洗缓存”功能。
