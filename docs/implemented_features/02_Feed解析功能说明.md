# Feed 解析功能说明

## 实现文件

主要文件：

```text
mercury_feed.py
mercury_storage.py
```

`mercury_feed.py` 负责 RSS / Atom / OPML 的解析逻辑，`mercury_storage.py` 负责拉取 Feed 并写入数据库。

## 已实现功能

1. RSS 解析：
   - 支持 `<rss>` 根节点。
   - 读取 channel 标题。
   - 读取 item 标题、链接、发布时间、作者、摘要。
   - 读取 `<guid>` 作为稳定文章 ID。
   - 给文章添加 `RSS` 标签。
2. Atom 解析：
   - 支持 `<feed>` 根节点。
   - 读取 entry 标题、链接、发布时间、作者、摘要/内容。
   - 读取 `<id>` 作为稳定文章 ID。
   - 给文章添加 `Atom` 标签。
3. OPML 导入：
   - 支持解析 `.opml` / `.xml`。
   - 读取 outline 的 `xmlUrl` / `xmlurl`。
   - 过滤无效 URL。
   - 去重重复订阅。
4. Feed 自动发现：
   - 如果输入的是网页 HTML，会尝试查找 `<link rel="alternate">` 中的 RSS / Atom 地址。
5. Feed 刷新：
   - 遍历所有订阅源。
   - 请求 Feed XML。
   - 解析文章。
   - 写入 SQLite。
   - 单个 Feed 失败不会中断其它 Feed。

## 数据规范

文章身份优先级：

```text
stable_id -> URL
```

RSS 使用 `<guid>` 作为 `stable_id`，Atom 使用 `<id>` 作为 `stable_id`。如果没有 stable id，则回退到 feed 内的 URL。

## 主要流程

### 添加订阅

1. 用户输入 URL。
2. `StorageService.add_feed()` 请求 URL。
3. `parse_feed_xml()` 解析 RSS / Atom。
4. Feed 写入 `feeds` 表。
5. 文章写入 `entries` 表。

### 刷新全部订阅

1. `StorageService.refresh_all()` 遍历 `feeds`。
2. 每个 Feed 单独请求和解析。
3. 成功的 Feed 更新文章。
4. 失败的 Feed 记录错误。
5. GUI 显示刷新成功或部分失败。

## 已知限制

1. 当前解析器基于 `xml.etree.ElementTree`，不是完整 `feedparser`。
2. 对复杂命名空间、非标准 RSS 字段、Feed JSON 的兼容性有限。
3. 当前只实现 OPML 导入，尚未实现 OPML 导出。
4. Feed 刷新依赖网络质量，部分源可能超时或拒绝访问。
