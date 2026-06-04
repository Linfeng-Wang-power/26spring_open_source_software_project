# Mercury PyQt Edition 测试报告

测试日期：2026-06-02  
测试环境：Windows / Conda 环境 `mercury-pyqt` / Python 3.11.15  
项目路径：`26spring_open_source_software_project-main`

## 1. 测试范围

本次测试覆盖当前仓库已实现的主要功能：

1. Python 依赖和项目模块导入。
2. Feed / OPML 基础解析。
3. Reader Pipeline：正文提取、HTML 清洗、Markdown 转换、Reader HTML 渲染。
4. SQLite 存储层：migrations、FeedStore、EntryStore、ContentStore、SettingsStore、StorageService 接口。
5. GUI 外壳离屏实例化。

未覆盖真实网络 Feed 同步、真实 GUI 交互、真实 LLM Provider、Summary Agent 和 Translation Agent，因为这些能力当前仍处在占位或未完整实现阶段。

## 2. 环境检查

`requirements.txt` 中列出的依赖均已安装，并且版本匹配。项目核心模块导入测试通过：

```text
project imports ok
```

注意：`pip check` 仍报告环境中额外包的依赖缺失：

```text
openai 2.14.0 缺少 distro / pydantic / sniffio / tqdm
opencv-python 4.9.0.80 缺少 numpy
tiktoken 0.12.0 缺少 regex / requests
jsonargparse 4.44.0 缺少 pyyaml
```

这些包不属于当前 `requirements.txt`，当前 Mercury 已实现功能未直接依赖它们。

## 3. 自动化测试结果

执行命令：

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONIOENCODING='utf-8'
& python -m pytest -q --basetemp 'pytest_tmp_run_utf8'
```

结果：

```text
37 passed, 1 warning in 5.50s
```

测试文件：

1. `tests/test_reader_pipeline.py`
2. `tests/test_storage.py`

覆盖到的能力：

1. Reader fetcher redirect 和 final URL 记录。
2. sanitizer 删除危险脚本并修复相对 URL。
3. HTML 到 Markdown 转换保留链接和图片。
4. ReaderPipeline 生成 ReaderDocument。
5. SQLite migration 建表和幂等性。
6. FeedStore / EntryStore / ContentStore / SettingsStore 基础行为。
7. StorageService 暴露当前 GUI 所需接口。
8. 存储层不 import Qt。

警告：

```text
yoyo 使用 pkg_resources，pkg_resources 已被 setuptools 标记为 deprecated。
```

当前环境已将 `setuptools` 固定到 `80.10.2`，否则 `yoyo-migrations==8.2.0` 在新版 setuptools 下无法导入 `pkg_resources`。

## 4. 手工冒烟测试

### 4.1 Feed / OPML 解析

测试内容：

1. 使用内联 RSS XML 调用 `parse_feed_xml()`。
2. 使用内联 OPML XML 调用 `parse_opml()`。

结果：

```text
Demo Feed 1 Hello 1 https://example.com/rss.xml
```

结论：基础 RSS 和 OPML 解析可用。

### 4.2 Reader Pipeline

测试内容：

1. 输入包含标题、段落、相对链接和 script 的 HTML。
2. 调用 `ReaderPipelineService.process_source_html()`。
3. 检查 script 被清理、相对链接被修复、Markdown 和 Reader HTML 被生成。

结果：

```text
Reader Test
True True True True
```

结论：Reader 管线核心路径可用。

### 4.3 GUI 外壳离屏实例化

测试命令使用 `QT_QPA_PLATFORM=offscreen`，并用 mock service 实例化 `MercuryMainWindow`。

结果：

```text
Mercury 4 9
```

结论：GUI 外壳可以被实例化；mock 数据下文章列表和订阅源列表可加载。

### 4.4 默认 StorageService 启动路径

沙箱内直接运行 `StorageService()` 时无法创建用户目录：

```text
PermissionError: \.mercury_pyqt
```

放行权限后复测通过：

```text
['All Feeds', 'Starred']
```

结论：默认数据目录路径在真实权限下可用；在受限沙箱中需要放行或改用测试数据库路径。

## 5. 发现的问题和风险

### P1. Windows 默认编码会导致 migration 读取失败

如果不设置 UTF-8 模式，`yoyo` 会按 Windows 默认 GBK 打开 SQL migration 文件，遇到中文注释时报错：

```text
UnicodeDecodeError: 'gbk' codec can't decode byte ...
```

影响：

1. Windows 下直接运行测试或首次初始化数据库可能失败。
2. GUI 默认启动时会调用 `StorageService()`，因此也可能受影响。

建议：

1. 在启动脚本或 README 中明确要求设置 `PYTHONUTF8=1`。
2. 更稳妥的做法是在迁移加载逻辑中确保 SQL 文件按 UTF-8 读取，或移除 migration SQL 文件中的非 ASCII 注释。

### P1. `StorageService()` 默认写入用户主目录，沙箱或受限权限下失败

默认数据库目录为：

```text
\.mercury_pyqt
```

在受限环境中创建该目录会失败。放行权限后可通过。

建议：

1. 为测试和开发提供显式 `db_path` 配置入口。
2. GUI 启动失败时给出清晰错误提示。
3. 后续考虑使用平台标准 app data 目录，而不是直接写用户主目录隐藏文件夹。

### P2. `setuptools` 新版本和 `yoyo-migrations==8.2.0` 存在兼容性风险

`yoyo` 依赖 `pkg_resources`，而新版本 setuptools 已移除或弱化该模块。

当前处理：

```text
setuptools==80.10.2
```

建议：

1. 在 `requirements.txt` 中补充 `setuptools<81`。
2. 后续评估升级 yoyo 或替换 migration 方案。

### P2. Summary / Translation / Provider 仍为接口或存储占位

当前 `SummaryStore`、`TranslationStore`、`ProviderStore` 的核心方法仍是 `NotImplementedError`。GUI 中 Summary / Translation 也仍使用 mock agent。

影响：

1. AI 摘要和翻译不是可验收的真实功能。
2. Provider 配置和 API key 管理尚未接入。

建议：

1. 先实现 ProviderStore 和 OpenAI-compatible Provider。
2. 再实现 SummaryAgent，并用 mocked provider 写测试。
3. 最后实现 Translation segmenter 和 TranslationAgent。

### P3. 环境中存在与项目无关的损坏依赖

`pip check` 中的 openai、opencv、tiktoken、jsonargparse 报错不影响当前功能，但会让环境健康检查变红。

建议：

1. 保持 Mercury 环境尽量干净，只安装项目需要的包。
2. 如果后续要使用 OpenAI SDK，再补齐 openai 的依赖。

## 6. 总体结论

当前已实现模块整体可测试，自动化测试在 UTF-8 模式下全部通过：

```text
37 passed
```

Feed / OPML、Reader Pipeline、存储 Store 层和 GUI 外壳的基础能力已经具备。当前最需要优先处理的是 Windows 编码和 migration 兼容性问题，否则首次启动和测试在不同机器上容易失败。

AI 相关能力目前还没有进入真实可用状态，后续开发应优先补齐 Provider、Summary Agent、Translation Agent 及对应测试。
