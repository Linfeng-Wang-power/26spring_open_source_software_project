# Mercury PySide6 RSS Reader

Mercury PySide6 RSS Reader 是一个本地优先的跨平台桌面 RSS 阅读器原型，应用窗口标题为 `Lumen`。项目使用 Python 与 PySide6 构建，支持订阅源管理、OPML 导入、文章阅读、正文清洗、标签、收藏、已读/未读、摘要与翻译等功能。

项目目标是做一个无需注册、无需登录、默认本地存储、可接入 OpenAI-compatible 大模型 Provider 的桌面阅读工具。

## 主要特性

1. 本地优先：
   - 用户数据默认存储在本机 SQLite 数据库。
   - 默认不需要注册、登录或云端部署。
   - API Key 优先保存到系统 keyring；不可用时可使用环境变量。

2. RSS / Atom 阅读：
   - 支持添加 RSS / Atom Feed。
   - 支持刷新全部订阅。
   - 支持 OPML 导入。
   - 单个订阅源刷新失败不会中断其它订阅源。

3. 三栏阅读界面：
   - 左侧：Feeds / Tags。
   - 中间：文章列表。
   - 右侧：Reader 阅读区。
   - 支持收藏、已读/未读、搜索、更多筛选。

4. Reader 清洗：
   - 抓取原文网页。
   - 提取正文内容。
   - 清洗 HTML、修复相对链接与图片地址。
   - 转换为 canonical Markdown。
   - 渲染为本地 Reader HTML。

5. 标签与批量操作：
   - 支持给文章添加 / 移除标签。
   - 支持按标签筛选文章。
   - 支持标签批量标已读、批量收藏、批量清洗。
   - 支持订阅源批量删除。

6. AI 摘要与翻译：
   - 支持 OpenAI-compatible Provider。
   - 支持摘要生成、批量摘要。
   - 支持全文翻译、划词翻译。
   - 摘要语言与翻译语言可以独立选择。

## 技术栈

| 模块 | 技术 |
|------|------|
| GUI | PySide6 / Qt 6 |
| 存储 | SQLite、yoyo-migrations |
| 网络请求 | httpx |
| Feed / OPML | xml.etree.ElementTree、自定义 RSS / Atom 解析 |
| Reader 清洗 | readability-lxml、BeautifulSoup4、bleach |
| Markdown | markdownify、markdown-it-py |
| AI Provider | OpenAI-compatible HTTP API |
| API Key | keyring，或 `OPENAI_API_KEY` 环境变量 |
| 测试 | pytest、pytest-qt、respx |

## 环境要求

建议环境：

```text
Python 3.11+
```

项目主要在 Python 3.11 环境下测试。桌面 GUI 依赖 Qt，因此建议使用虚拟环境或 conda 环境，避免和系统 Python 混用。

## 安装与运行

### 1. 克隆或进入项目目录

```bash
cd /path/to/26spring_open_source_software_project
```

### 2. 创建虚拟环境

使用 venv：

```bash
python3.11 -m venv .venv
source .venv/bin/activate
```

或使用 conda：

```bash
conda create -n mercury python=3.11
conda activate mercury
```

### 3. 安装依赖

请使用：

```bash
pip install -r requirements.txt
```

不要使用 `pip install requirements`。后者会尝试安装名为 `requirements` 的包，而不是读取本项目的依赖文件。

### 4. 启动应用

推荐方式：

```bash
python -m mercury
```

也可以使用打包入口脚本：

```bash
python run_lumen.py
```

## 数据存储位置

默认本地数据目录：

```text
~/.mercury_pyqt/
```

默认数据库文件：

```text
~/.mercury_pyqt/mercury.db
```

数据库中保存订阅源、文章、标签、清洗缓存、摘要结果、翻译结果和基础设置。API Key 不应写入 SQLite，项目会优先通过系统 keyring 保存。

## 功能使用说明

### 添加订阅源

1. 点击左侧 Feeds 区标题旁的 `+` 按钮。
2. 输入 RSS / Atom Feed URL，或输入支持自动发现 Feed 的网页 URL。
3. 应用会在后台请求并解析订阅源。
4. 添加成功后左侧列表和文章列表会刷新。

### 导入 OPML

1. 点击顶部工具栏的 `订阅` 菜单。
2. 选择 `导入 OPML`。
3. 选择 `.opml` 或 `.xml` 文件。
4. 应用会导入其中的订阅源，并跳过重复或无效 URL。

### 刷新订阅

1. 点击顶部工具栏的 `刷新`。
2. 应用会在后台刷新所有订阅源。
3. 单个订阅失败不会中断整体刷新。
4. 刷新结果会显示在底部导航栏。

### 阅读文章

1. 在左侧选择 `All Feeds`、`Starred`、某个 Feed 或某个 Tag。
2. 在中间文章列表选择文章。
3. 右侧 Reader 会显示文章内容。
4. 未读文章被打开后会自动标记为已读。
5. 点击文章列表中的星标按钮可以收藏或取消收藏。

### 更多筛选

文章列表顶部的 `...` 按钮提供更多筛选：

```text
显示全部
只看未读
只看星标
清除搜索
```

在 Tags 页面使用未读筛选时，左侧仍会保持在 Tags 页面，不会跳回 Feeds。

### 搜索文章

在顶部搜索框输入关键词，可以过滤当前文章列表。搜索范围包括标题和摘要。

也可以输入：

```text
tag:标签名
```

按标签快速搜索文章。

### 标签功能

1. 选择文章后，可以通过工具栏给文章添加标签。
2. 切换左侧 `Tags` 标签页，可以按标签浏览文章。
3. 在 Tags 页面，可以对当前标签下的文章执行批量操作：
   - 标签标已读。
   - 标签批量收藏。
   - 标签批量清洗。

### 清洗文章

1. 选择一篇文章。
2. 点击工具栏的 `清洗`。
3. 应用会在后台抓取原文网页并提取正文。
4. 清洗结果会保存到本地数据库。
5. Reader 区会显示清洗后的排版。

清洗流程大致为：

```text
source_html -> cleaned_html -> canonical_markdown -> reader_html
```

如果想回到 Feed 原始摘要显示，可以点击 `还原显示`。

### 查看原文与返回

清洗后的 Reader 顶部会显示 `查看原文` 链接。

1. 点击 `查看原文` 后，应用会在内部浏览器中打开原网页。
2. 底部导航状态会显示原文加载状态。
3. 点击 Reader 顶部的 `返回` 按钮，可以回到清洗后的阅读页。

### 摘要

1. 先在底部导航栏选择摘要语言。
2. 点击 `生成摘要`。
3. 摘要会在底部摘要面板中流式显示。
4. 再次点击摘要任务时，如果任务正在运行，会请求取消当前任务。

摘要语言支持：

```text
跟随界面
中文
英文
日文
```

### 批量摘要

1. 在文章列表中使用 Ctrl 或 Shift 选择多篇文章。
2. 点击顶部工具栏中的 `批量摘要`。
3. 应用会按顺序处理选中的文章。
4. 批量处理结果会逐条显示。

### 翻译

1. 在底部导航栏选择翻译语言。
2. 点击 `翻译`。
3. 翻译结果会显示在底部翻译面板中。
4. 翻译进度会按段落更新，并保存成功段落。

翻译语言支持：

```text
译中文
译英文
译日文
```

摘要语言和翻译语言互相独立，可以分别选择不同语言。

### 划词翻译

1. 在 Reader 中选中一段文字。
2. 稍等片刻后会弹出划词翻译浮层。
3. 浮层可以拖动边缘调整大小。
4. 划词翻译使用当前翻译语言。

### 底部摘要 / 翻译面板

底部区域包含摘要面板和翻译面板：

1. 可以拖动整体高度，给 Reader 区留出更多空间。
2. 摘要和翻译两个框之间也可以单独拖动调整。
3. 如果摘要和翻译都关闭，底部区域会自动收回到最小高度。

## AI Provider 配置

点击顶部工具栏的 `设置`，填写：

```text
Base URL
Model
API Key
摘要详细程度
```

Provider 采用 OpenAI-compatible Chat Completions 风格接口。常见配置示例：

```text
Base URL: https://api.openai.com/v1
Model: gpt-4o-mini
```

API Key 保存规则：

1. 优先保存到系统 keyring。
2. 如果 keyring 不可用，可以使用环境变量：

```bash
export OPENAI_API_KEY="你的 API Key"
```

自动化测试不会调用真实 LLM API。

## 运行测试

安装依赖后，可以运行：

```bash
pytest
```

也可以只运行 GUI 和 Reader 相关测试：

```bash
pytest tests/test_gui_smoke.py tests/test_reader_pipeline.py
```

如果使用 conda 环境示例：

```bash
/opt/anaconda3/envs/kaiyuan2/bin/python -m pytest tests/test_gui_smoke.py tests/test_reader_pipeline.py
```

当前环境中可能看到如下 warning：

```text
yoyo/migrations.py: pkg_resources is deprecated as an API
```

这是 `yoyo-migrations` 对 `pkg_resources` 的弃用提示，不影响当前功能运行。项目已在 `requirements.txt` 中限制 `setuptools<81`，用于避免依赖兼容问题。

## 打包说明

项目当前以源码运行和 PyInstaller MVP 打包为主。仓库中提供了 macOS 打包脚本：

```bash
./build_dmg.sh
```

打包时需要注意：

1. 只保留一个 Qt binding 环境，避免 PySide6 / PyQt6 混装。
2. 需要收集 Qt platform plugins、image plugins、translations 和 WebEngine 资源。
3. 应测试打包后的应用，而不只测试源码运行。

## 常见问题

### 1. PySide6 未安装

现象：

```text
ModuleNotFoundError: No module named 'PySide6'
```

解决：

```bash
pip install -r requirements.txt
```

### 2. 点击摘要或翻译提示需要配置 Provider

需要先进入 `设置`，填写 OpenAI-compatible Provider 的 Base URL、Model 和 API Key。

### 3. Feed 添加失败

可能原因：

1. URL 不是有效的 `http://` 或 `https://` 地址。
2. 目标网站不是 RSS / Atom Feed。
3. 目标网站阻止请求或网络超时。
4. 自动发现 Feed 失败。

可以尝试直接输入 RSS / Atom XML 地址。

### 4. 原文网页打不开或图片不显示

可能原因：

1. 网站阻止第三方客户端访问。
2. 图片需要 Referer 或鉴权。
3. 网站使用复杂懒加载或脚本渲染。
4. 网络超时。

Reader 清洗会尽量修复相对链接、懒加载图片地址和 `srcset` 图片，但不保证所有网站都能完整还原。

### 5. yoyo 的 pkg_resources warning

这是依赖层的弃用提示，当前不影响运行。项目通过 `setuptools<81` 限制规避未来兼容风险。

## 项目结构

```text
mercury/
  app/                 应用入口
  agent/               摘要、翻译、Provider、Prompt 模板
  reader/              原文抓取、清洗、Markdown 转换、Reader 渲染
  resources/prompts/   内置摘要与翻译 Prompt 模板
  migrations/          SQLite schema migration
  feed.py              Feed / OPML 解析逻辑
  gui.py               PySide6 GUI 主窗口
  storage.py           SQLite 存储服务
tests/                 自动化测试
docs/                  阶段性实现说明
```

## 成员名单

| 姓名 | GitHub账号 | 学号 |
|------|------------|------|
| 汪琳丰 | linfengwang1009@163.com | 51285903095 |
| 陈亦楠 | ynchen@stu.ecnu.edu.cn  | 51285903083 |
| 晏康佳 | faiz55520030505@163.com | 51285903117 |
| 张睿桐 | 1244645916@qq.com       | 51285903135 |
| 周珠晗 | zhaociyuewan@outlook.com| 51285903123 |
| 卢雨凝 | ynlu@stu.ecnu.edu.cn    | 51285903096 |
| 陆骏凯 | pandajunkai@163.com     | 51285903114 |
| 张洳维 | ruruweizhang@gmail.com  | 50255903002 |

## License

本项目使用仓库中的 [LICENSE](LICENSE) 文件所声明的许可证。
