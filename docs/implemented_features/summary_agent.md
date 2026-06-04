# Summary Agent 实现说明

> 分支：`summary-agent` · 负责人：陆骏凯 · 状态：MVP 完成（端到端可跑通）

## 1. 功能概览

为 Lumen 阅读器接入「一键生成摘要」能力：用户在 Reader 内点击 *生成摘要*，
应用通过用户配置的 OpenAI 兼容 Provider 流式拉取摘要，按字打印到 SummaryBar，
成功后写入 SQLite，再次打开同一篇文章直接回放缓存。

满足约束：

- 本地优先：摘要文本写入 `summary_results` 表，API key 走 OS keyring，不进 SQLite，不进日志。
- 模型中立：所有 Provider 调用走 `LLMProvider` Protocol，目前实现 `OpenAICompatibleProvider`。
- 跨平台：keyring 自动适配 macOS Keychain / Windows Credential Locker / Linux SecretService。
- GUI 不阻塞：流式拉取在 `QThread` 上跑，token 在 worker 端 buffer + 80ms 节流后发回主线程。

## 2. 模块结构

```
agent/
  provider/
    llm_provider.py        # Protocol + ProviderConfig + 统一异常
    openai_compatible.py   # httpx 实现，complete() / stream()，SSE 解析，错误映射
    keys.py                # keyring + 环境变量 fallback；store/resolve API key
  prompts/
    template_renderer.py   # YAML 加载、变量校验、format_map 渲染、模板指纹
  summary/
    summary_agent.py       # SummaryAgent / SummaryRequest / SummaryResult
    summary_worker.py      # QObject worker，节流 emit token chunk
    runtime_config.py      # 从 SettingsStore + keyring 装配 SummaryAgent

resources/prompts/
  summary.default.yaml     # 含 {target_language} {detail_level} {title} {content}

mercury_storage.py
  SummaryStore             # save_result / get / get_metadata / delete

mercury_gui.py
  SummarySettingsDialog    # base_url / model / api_key / 详细度 用户配置
  on_summary               # 投递 worker、流式更新、取消、保存
```

## 3. 数据流

1. 用户点 *生成摘要*：`MainWindow.on_summary` 校验 Provider，必要时弹设置对话框。
2. 输入：`ContentStore.canonical_markdown` 优先，无则回退 `Article.summary`。
3. `SummaryAgent.stream_iter` 用 YAML 模板拼出 `messages`，调 `provider.stream()`。
4. `SummaryWorker` 累积 token，每 80ms `emit token(job_id, entry_id, chunk)`。
5. 主线程比对 `job_id + entry_id`，仅当仍是当前任务时更新 `summary_text`。
6. 成功：`SummaryStore.save_result(entry_id, full_text, "model@<fingerprint>")`。
7. 切文章：`_restore_summary_for_article` 调 `SummaryStore.get` 回放缓存。

## 4. 关键决策

| 决策 | 选择 | 说明 |
|------|------|------|
| 调用模式 | 流式 SSE | UI 打字机效果；Worker 端节流避免冲爆 GUI |
| 输入字段 | Markdown 主，RSS summary 兜底 | 减少广告、导航杂讯 |
| 目标语言 | `SettingsStore.current_language()`，默认 zh-CN | UI 已有语言切换 |
| 详细度 | `short` / `default` / `detailed`，写入 `summary.detail` | 设置对话框三选一 |
| 取消语义 | 同一按钮二次点击 = 取消；切文章不取消 | 与 AGENTS.md §4.6 一致 |
| 失败处理 | 失败/取消不写库 | 不覆盖既有成功摘要 |
| 模型标识 | `model@<8-char-template-sha>` | 写入 `summary_results.model_id` |
| API key | keyring 优先，`OPENAI_API_KEY` 兜底 | 永不进 SQLite/日志 |

## 5. Provider 配置

GUI 入口：工具栏 *设置*。三项必填：

- **Base URL**：OpenAI 兼容根（接受 `https://x.com`、`https://x.com/v1`、
  或完整 `https://x.com/v1/chat/completions`）。
- **模型**：模型 ID。
- **API Key**：保存到系统 keyring。留空表示「保留已有 key」。

环境变量后备：`MERCURY_LLM_BASE_URL` / `MERCURY_LLM_MODEL` / `OPENAI_API_KEY`。
当 keyring 不可用时，UI 会提示用环境变量。

## 6. 测试

| 文件 | 覆盖 |
|------|------|
| `tests/test_summary_template.py` | YAML 加载、变量校验、缺失变量报错、指纹稳定性 |
| `tests/test_summary_agent.py` | run/stream/stream_iter，detail_level 校验，错误透传 |
| `tests/test_openai_compatible.py` | base_url 三种形态、SSE 解析、超时/401/5xx 映射、API key 不入 body（respx mock） |
| `tests/test_summary_store.py` | save/get/delete、空文本拒绝、覆盖语义 |

```
pytest -q --ignore=tests/test_gui_smoke.py
# Phase 2 后约 100+ passed
pytest tests/test_gui_smoke.py
# 3 passed (pytest-qt)
```

## 7. 进度

- [x] 设计与 spec 评审
- [x] `LLMProvider` Protocol + OpenAI 兼容实现 + SSE 流式
- [x] keyring 跨平台 API key 解析
- [x] YAML prompt 模板系统 + 内置 `summary.default`
- [x] `SummaryAgent` + `SummaryRequest` / `SummaryResult`
- [x] `SummaryStore` 真实实现（覆盖既有 `NotImplementedError` stub）
- [x] `SummaryWorker`（QThread，节流流式）
- [x] GUI 接线：on_summary、文章切换回放、取消、错误展示
- [x] `SummarySettingsDialog`（base_url / model / api_key / 详细度 / 测试连接按钮）
- [x] 端到端测试 100+ 全过
- [x] Phase 2：超长内容裁剪（`max_content_chars` 默认 12000，60/40 头尾切片 + 省略提示）
- [x] Phase 2：targetLanguage 切换器（SummaryBar 下拉，持久化到 `summary.target_lang`）
- [x] Phase 2：批量摘要（多选 + 串行 worker + 进度对话框 + 失败聚合）
- [x] Phase 3：迁移到 `mercury/` 包布局（`mercury.agent.*` / `mercury.reader.*` / `mercury.gui` / `mercury.storage` / `mercury.feed`），入口改为 `python -m mercury` 或 `run_lumen.py`

## 8. 已知限制

1. ~~暂不支持文章超长时主动裁剪~~ → 已在 Phase 2 实现，`SummaryRequest.max_content_chars` 默认 12000，
   超长时 60/40 头尾切片并插入 `[…内容因长度限制已裁剪…]` 提示。`SummaryResult.truncated` 携带标记。
2. Provider 设置只支持单 profile（无多 Provider 切换）。
3. ~~翻译目标语言取自 `SettingsStore.current_language()`~~ → 已在 SummaryBar 加下拉「跟随界面/中文/英文/日文」，写入 `summary.target_lang`。
4. 系统 keyring 失败时需手动用环境变量；未提供 GUI fallback。
5. 批量摘要使用非流式调用；进度对话框关闭即视为取消（剩余 entry 计入 skipped）。

## 9. 下一步衔接点

- `TranslationAgent`（张睿桐）：可直接复用 `agent/provider`、`agent/prompts`、`SummaryWorker` 节流模式。
- `AgentRuntime`（共享 task queue）：当前 worker 直接挂在 `MainWindow`，未来抽到 `core/tasking/` 后只需替换工厂。
