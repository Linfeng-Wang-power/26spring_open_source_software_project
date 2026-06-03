# macOS 测试计划

## 1. 目标

- 验证已提交模块在 macOS 上按预期工作。
- 补齐自动化测试覆盖：单元测试、GUI smoke 测试、HTTP mock 测试。
- 形成可复现的测试记录和汇报材料。

## 2. 当前范围

已完成模块：

- GUI Shell：`mercury_gui.py`
- Feed / OPML：`mercury_feed.py`
- Reader Pipeline：`reader/`
- Local Storage：`mercury_storage.py`，`migrations/0001–0005`

现有自动化测试：

- `tests/test_reader_pipeline.py`
- `tests/test_storage.py`

待补充测试：

- `tests/test_gui_smoke.py`
- `tests/test_feed_sync.py`
- macOS 测试记录与汇报文档

## 3. macOS 环境准备

- Python 3.11
- 建议创建虚拟环境：
  - `python3 -m venv .venv`
  - `source .venv/bin/activate`
- 安装依赖：`pip install -r requirements.txt`
- 推荐启用 UTF-8 模式：`export PYTHONUTF8=1`
- 运行命令：
  - `pytest -q`
  - `pytest -q tests/test_reader_pipeline.py tests/test_storage.py`
  - `pytest -q tests/test_gui_smoke.py`
  - `pytest -q tests/test_feed_sync.py`

## 4. 测试项

### 4.1 单元测试（`pytest`）

- 验证 `reader/` 各个节点：fetcher、readability、sanitizer、markdown_converter、html_renderer。
- 验证 `mercury_storage.py` 与 migrations：数据库创建、迁移、CRUD。
- 验证 `mercury_feed.py`：RSS/Atom 解析、OPML 导入、字段规范。
- 目标：现有测试保持通过；新增缺失功能测试。

### 4.2 GUI Smoke 测试（`pytest-qt`）

- 使用 `QT_QPA_PLATFORM=offscreen` 离屏实例化主窗口。
- 验证：
  - 主窗口可创建。
  - 三栏布局（订阅源、文章列表、阅读区）可见。
  - 工具栏、标题栏、状态栏存在。
- 交付文件：`tests/test_gui_smoke.py`

### 4.3 HTTP Mock 测试（`httpx.MockTransport` / `respx`）

- 目标：Feed 同步测试不依赖真实网络。
- 测试场景：
  - 模拟 RSS/Atom 成功响应，检查 `mercury_feed.py` 解析结果。
  - 模拟 OPML 导入。
  - 模拟网络失败 / 超时，验证异常处理。
- 交付文件：`tests/test_feed_sync.py`

### 4.4 手工验收

- 运行 `python mercury_gui.py` 或等效启动方式。
- 验证：
  - 左侧订阅源面板、文章列表、阅读区正常显示。
  - 本地存储目录能正常创建。
  - 阅读器可渲染基础 HTML 正文。
- 若条件允许，参考 `TEST_REPORT.zh.md` 中的 Windows 结果进行对比。

## 5. 执行步骤

1. 进入项目目录：`cd /Users/rrruuu/school/ecnu/class/openSoft/project`
2. 创建并激活虚拟环境。
3. 安装依赖。
4. 先运行已有测试：`pytest -q tests/test_reader_pipeline.py tests/test_storage.py`
5. 编写并运行新增测试：`tests/test_gui_smoke.py`、`tests/test_feed_sync.py`
6. 记录测试结果和环境信息。
7. 在 `tests/test_mac_plan.md` 更新执行状态。
8. 形成汇报材料：结果、问题、风险、修复建议。

## 6. 验收标准

- `pytest -q` 全部通过。
- GUI 离屏 smoke test 通过。
- HTTP mock feed sync 测试通过。
- `mercury_feed.py`、`reader/`、`mercury_storage.py` 模块在本地运行无明显异常。
- 形成完整测试文档记录。

## 7. 风险与建议

- `yoyo` 迁移依赖 `setuptools` 版本，建议在 macOS 上也确认 `PYTHONUTF8=1`。
- 如果 `mercury_gui.py` 使用 PySide6，需确认 `pytest-qt` 版本兼容性。
- 若默认存储路径写入用户主目录，测试时应优先使用显式测试数据库路径以避免权限问题。
- Summary / Translation Agent 目前仍未完成，后续测试计划应进一步补齐这两部分。
