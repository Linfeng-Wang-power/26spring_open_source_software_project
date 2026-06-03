# Mercury macOS 测试计划

负责人：张洳维  
测试平台：macOS  
计划日期：2026-06-04  
参考文档：`PLAN.md`、`AGENTS.md`、`README.md`、`TEST_REPORT.zh.md`

## 1. 测试目标

本计划用于验证当前已经提交并标记为 Done 的模块能否在 macOS 上正确安装、运行和测试，并形成后续测试记录与汇报材料。

本轮只验收已经完成的四个模块：

| Module | Owner | Deliverable | macOS 测试重点 |
|---|---|---|---|
| GUI Shell | 卢雨凝 | `mercury_gui.py` | PySide6 能否安装；主窗口是否能在离屏和真实 macOS 桌面启动；三栏布局、工具栏、状态栏是否存在 |
| Feed / OPML | 汪琳丰 | `mercury_feed.py` | RSS / Atom 解析、OPML 导入、`httpx` mock 同步、失败 feed 不影响整体刷新 |
| Reader Pipeline | 周珠晗 | `reader/` | fetch redirect、readability、HTML sanitizer、Markdown 转换、Reader HTML 渲染 |
| Local Storage | 陈亦楠 | `mercury_storage.py`、`migrations/0001`-`0005` | SQLite migration、9 张业务表、Store CRUD、默认本地数据库路径、存储层不依赖 Qt |

暂不作为真实功能验收：

1. Summary Agent。
2. Translation Agent。
3. 真实 LLM Provider。
4. 真实外网 RSS 批量同步。
5. DMG 打包和签名。

这些功能目前仍处于接口、mock 或后续里程碑状态，可以在汇报中列为风险和后续工作。

## 2. 项目功能理解

Mercury PyQt Edition 是一个本地优先的跨平台桌面 RSS 阅读器，目标是无注册、无登录、无云部署，用户数据默认保存在本机。当前仓库采用 Python 3.11+ 与 PySide6，主要功能边界如下：

1. `mercury_gui.py` 提供桌面 GUI 外壳，包含订阅源侧栏、文章列表、Reader 阅读面板、工具栏和状态栏。
2. `mercury_feed.py` 提供 Feed / OPML 能力，支持 RSS、Atom、OPML 解析，并通过 `httpx` 获取订阅源内容。
3. `reader/` 提供阅读管线，目标流程是 `source_html -> cleaned_html -> canonical_markdown -> reader_html`。
4. `mercury_storage.py` 提供本地 SQLite 存储，使用 yoyo migration 管理 schema，当前包含 feeds、entries、contents、tags、summary / translation / provider / agent / settings 相关表。

## 3. macOS 环境准备

### 3.1 当前测试环境

```bash
cd /Users/rrruuu/school/ecnu/class/openSoft/project
softvenv/bin/python --version
```

当前采用仓库内已有虚拟环境 `softvenv`。本机探测结果：

```text
Python 3.14.4
```

说明：

1. 项目文档要求 Python 3.11+，`softvenv` 的 Python 3.14.4 满足版本下限。
2. Python 3.14 下 yoyo / sqlite3 会产生较多 deprecation warnings，应记录为环境风险，但当前不影响已完成模块的功能测试。
3. 所有正式测试命令都直接使用 `softvenv/bin/python`，避免误用系统默认 `python3`。

### 3.2 环境检查命令

```bash
cd /Users/rrruuu/school/ecnu/class/openSoft/project
softvenv/bin/python --version
softvenv/bin/python -m pip check
softvenv/bin/python - <<'PY'
import PySide6
import httpx
import yoyo
import bleach
import markdownify
print("project dependencies import ok")
PY
```

预期：

1. Python 版本为 `Python 3.14.4`。
2. 核心依赖可以导入。
3. `pip check` 没有项目依赖冲突；如果出现与 Mercury 无关的全局包冲突，应记录但不直接判为项目失败。

## 4. 自动化测试计划

### 4.1 首选分组执行

macOS 下建议分组执行，而不是一开始就只跑全量命令。原因是 GUI 测试需要 Qt 平台插件，存储层的 `test_no_qt_import` 又希望验证没有 Qt 模块出现在当前 Python 进程中，两类测试放在同一个进程里容易互相污染。

#### A. Feed / Reader / GUI smoke

```bash
cd /Users/rrruuu/school/ecnu/class/openSoft/project
QT_QPA_PLATFORM=offscreen softvenv/bin/python -m pytest tests/test_feed_sync.py tests/test_feed_parsing.py tests/test_reader_pipeline.py tests/test_gui_smoke.py -q
```

预期：

```text
21 passed, 1 warning
```

覆盖点：

1. RSS XML 解析。
2. Atom XML 解析。
3. OPML 解析。
4. `LocalFeedService.add_feed()` 使用 mocked `httpx.get`。
5. `LocalFeedService.refresh_all()` 对失败 feed 记录错误但保留成功结果。
6. Reader fetcher 跟随 redirect 并记录 final URL。
7. sanitizer 删除 script / onerror 并修复相对链接。
8. HTML 到 Markdown 转换保留链接和图片。
9. ReaderPipeline 生成 `ReaderDocument`。
10. 合法 XML 形状但不是 feed 的 HTML 被拒绝。
11. malformed HTML 响应被识别为网页 HTML。
12. 普通网页中的 RSS link 可以被自动发现并继续解析。
13. 添加 feed 后 JSON cache 可落盘。
14. 非法 URL 不会写入订阅和文章状态。
15. GUI 主窗口离屏实例化，检查三栏布局、工具栏、Reader、FeedList、ArticleList、状态栏。
16. GUI 使用测试专用 service stub 加载 feed、文章和 Reader 内容。
17. GUI 搜索框能隐藏和恢复文章行。

#### B. Storage 功能测试

```bash
cd /Users/rrruuu/school/ecnu/class/openSoft/project
softvenv/bin/python -m pytest tests/test_storage.py -q -k "not test_no_qt_import"
```

预期：

```text
37 passed, 1 deselected, 1055 warnings
```

覆盖点：

1. yoyo migrations 创建全部业务表。
2. migrations 幂等。
3. `FeedStore` upsert / list / get / delete。
4. `EntryStore` upsert / filter / read / starred / tag / cascade delete。
5. `ContentStore` save / get / overwrite。
6. `SettingsStore` default / get / set / overwrite。
7. `StorageService` 提供 GUI 所需接口。

#### C. Storage 无 Qt 依赖测试

```bash
cd /Users/rrruuu/school/ecnu/class/openSoft/project
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 softvenv/bin/python -m pytest tests/test_storage.py::test_no_qt_import -q
```

预期：

```text
1 passed, 1 warning
```

说明：

1. `pytest-qt` 插件会在测试会话中导入 PySide6。
2. 因此验证存储层不依赖 Qt 时，需要禁用 pytest 插件自动加载，或改成独立子进程测试。
3. 如果不禁用插件，该测试可能失败，但失败不一定代表 `mercury_storage.py` 真的 import Qt。

### 4.2 全量测试命令

```bash
cd /Users/rrruuu/school/ecnu/class/openSoft/project
QT_QPA_PLATFORM=offscreen softvenv/bin/python -m pytest -q
```

当前风险：

1. 如果 `test_no_qt_import` 与 pytest-qt 在同一进程运行，全量测试可能出现 1 个失败。
2. 更稳妥的验收口径是采用 4.1 的分组执行结果。
3. 后续可以修改 `test_no_qt_import`，将它改为子进程导入检查，之后再恢复全量测试必须全绿。

### 4.3 本机已探测到的结果

在当前机器的 `softvenv` 环境下，Python 版本为 3.14.4，最新探测结果如下：

```text
python3 -m pytest -q
失败：默认 Homebrew Python 3.14 未安装 pytest。

softvenv/bin/python -m pytest -q
失败：macOS Cocoa QApplication 初始化 abort，原因是 QT_QPA_PLATFORM=offscreen 设置太晚。

QT_QPA_PLATFORM=offscreen softvenv/bin/python -m pytest tests/test_feed_sync.py tests/test_feed_parsing.py tests/test_reader_pipeline.py tests/test_gui_smoke.py -q
结果：21 passed, 1 warning。

softvenv/bin/python -m pytest tests/test_storage.py -q -k "not test_no_qt_import"
结果：37 passed, 1 deselected, 1055 warnings。

PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 softvenv/bin/python -m pytest tests/test_storage.py::test_no_qt_import -q
结果：1 passed, 1 warning。

QT_QPA_PLATFORM=offscreen softvenv/bin/python -m pytest -q
结果：58 passed, 1 failed, 1055 warnings。失败项为 tests/test_storage.py::test_no_qt_import，原因仍是 pytest-qt/PySide6 污染当前测试进程。
```

这些结果应写入正式测试报告的“macOS 环境差异与风险”部分。

## 5. 手工测试计划

### 5.1 GUI 真实启动

```bash
cd /Users/rrruuu/school/ecnu/class/openSoft/project
softvenv/bin/python mercury_gui.py
```

检查项：

1. 应弹出标题为 `Lumen` 的窗口。
2. 左侧为 feed 列表，中间为文章列表，右侧为 Reader 内容区。
3. 顶部工具栏存在刷新、添加 feed、导入 OPML、摘要、翻译等入口。
4. 点击不同 feed，文章列表应更新。
5. 点击不同文章，Reader 面板应更新标题、元信息、标签和正文。
6. 点击 Summary / Translation 时，目前允许出现 mock 或占位结果，但要记录“非真实 AI 功能”。

记录方式：

1. 截图：主窗口启动成功。
2. 截图：选择某篇文章后的 Reader 面板。
3. 记录异常：如果出现 Qt platform plugin、权限、字体显示、窗口无法显示等问题，复制完整报错。

### 5.2 Feed / OPML 手工验证

准备一个临时 OPML 文件，例如 `/tmp/mercury_test.opml`：

```xml
<?xml version="1.0" encoding="UTF-8"?>
<opml version="2.0">
  <body>
    <outline text="Example Blog" xmlUrl="https://example.com/feed.xml" />
  </body>
</opml>
```

验证方式：

```bash
softvenv/bin/python - <<'PY'
from mercury_feed import parse_opml
text = open("/tmp/mercury_test.opml", encoding="utf-8").read()
items = parse_opml(text)
print(items)
PY
```

预期：

1. 输出包含 `Example Blog`。
2. 输出包含 `https://example.com/feed.xml`。

真实网络 feed 同步只作为探索测试，不作为自动化验收。若测试真实 RSS 地址，需要记录网络环境、URL、HTTP 状态和失败原因。

### 5.3 Reader Pipeline 手工验证

```bash
softvenv/bin/python - <<'PY'
from reader.pipeline import ReaderPipelineService

html = """
<html><body>
  <article>
    <h1>Mac Reader Test</h1>
    <p>Hello Mercury.</p>
    <a href="/about">About</a>
    <script>alert(1)</script>
  </article>
</body></html>
"""

doc = ReaderPipelineService().process_source_html(
    html,
    source_url="https://example.test/posts/one",
)
print(doc.title)
print("script" not in doc.reader_html)
print("https://example.test/about" in doc.cleaned_html)
print("Hello Mercury." in doc.canonical_markdown)
PY
```

预期：

```text
Mac Reader Test
True
True
True
```

### 5.4 默认 StorageService 启动路径

```bash
softvenv/bin/python - <<'PY'
from mercury_storage import StorageService, DB_PATH
svc = StorageService()
print(DB_PATH)
print([feed.title for feed in svc.list_feeds()])
PY
```

预期：

1. 默认数据库路径为 `~/.mercury_pyqt/mercury.db`。
2. 输出至少包含 `All Feeds` 和 `Starred`。
3. 若 macOS 权限阻止创建用户目录，需要记录 `PermissionError`，并说明使用测试时传入 `db_path=tmp_path` 可规避。

## 6. 测试记录文档计划

建议后续新增或更新以下文档：

1. `TEST_REPORT_MAC.zh.md`：macOS 正式测试报告。
2. `tests/test_mac_plan.md`：本文件，保留为测试计划和执行清单。
3. 汇报材料截图目录：可以使用 `docs/images/mac-test/` 或汇报 PPT 自己的图片目录。

`TEST_REPORT_MAC.zh.md` 建议结构：

```markdown
# Mercury PyQt Edition macOS 测试报告

测试日期：
测试人员：张洳维
测试环境：

## 1. 测试范围
## 2. 环境检查
## 3. 自动化测试结果
## 4. 手工测试结果
## 5. 发现的问题和风险
## 6. 与 Windows 测试结果对比
## 7. 总体结论
```

每条测试记录建议包含：

| 字段 | 内容 |
|---|---|
| Case ID | 例如 `MAC-AUTO-001` |
| 模块 | GUI / Feed / Reader / Storage |
| 命令或操作 | 实际执行的命令或手工步骤 |
| 预期结果 | 测试前定义的通过标准 |
| 实际结果 | 命令输出、截图编号、异常信息 |
| 结论 | Pass / Fail / Blocked |
| 备注 | macOS 特有风险、与 Windows 差异 |

## 7. 风险和后续建议

| 优先级 | 问题 | 影响 | 建议 |
|---|---|---|---|
| P1 | macOS GUI 测试必须在进程启动前设置 `QT_QPA_PLATFORM=offscreen` | 否则 pytest-qt 创建 QApplication 时可能走 Cocoa 并 abort | 将环境变量放到测试命令、CI 配置或 `pytest.ini` 中 |
| P1 | `test_no_qt_import` 易受 pytest-qt 插件污染 | 全量测试可能出现假失败 | 改为子进程测试，或单独使用 `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` 执行 |
| P2 | 当前 `softvenv` 使用 Python 3.14.4 | 项目要求 Python 3.11+，但依赖在 3.14 下会产生额外兼容性警告 | 本轮按用户要求使用 `softvenv`，报告中记录 warning，不把 warning 直接判为失败 |
| P2 | yoyo 使用 `pkg_resources`，存在弃用警告 | 未来 setuptools 版本可能影响 migration | 已在 `requirements.txt` 中限制 `setuptools<81`，后续可评估升级 yoyo |
| P2 | 默认数据库写入 `~/.mercury_pyqt` | 沙箱或受限权限下可能失败 | 测试使用临时 `db_path`；GUI 启动失败时应给清晰提示 |
| P3 | Summary / Translation 仍非真实功能 | 汇报时不能宣称 AI 功能已完整可用 | 在测试报告中明确当前为接口或 mock 阶段 |

## 8. 执行清单

- [ ] 确认使用仓库内 `softvenv`。
- [ ] 确认 `softvenv` 已安装 `requirements.txt`。
- [ ] 记录 `softvenv/bin/python --version`、`pip check` 和核心依赖导入结果。
- [ ] 执行 Feed / Reader / GUI smoke 分组测试。
- [ ] 执行 Storage 功能测试。
- [ ] 执行 Storage 无 Qt 依赖隔离测试。
- [ ] 手工启动 `softvenv/bin/python mercury_gui.py` 并截图。
- [ ] 手工验证 OPML 解析。
- [ ] 手工验证 Reader Pipeline。
- [ ] 手工验证默认 `StorageService()` 路径。
- [ ] 汇总 macOS 与 Windows 测试差异。
- [ ] 写入 `TEST_REPORT_MAC.zh.md`。
