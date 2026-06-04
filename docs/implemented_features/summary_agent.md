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
mercury/
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
      batch_worker.py        # BatchSummaryWorker，串行执行多文章摘要
      runtime_config.py      # 从 SettingsStore + keyring 装配 SummaryAgent
  resources/prompts/
    summary.default.yaml     # 含 {target_language} {detail_level} {title} {content}
  storage.py
    SummaryStore             # save_result / get / get_metadata / delete
  gui.py
    SummarySettingsDialog    # base_url / model / api_key / 详细度 用户配置
    BatchSummaryDialog       # 批量摘要进度对话框
    on_summary               # 投递 worker、流式更新、取消、保存
    on_batch_summary         # 多选文章串行摘要
```

入口：`python -m mercury` 或 `python run_lumen.py`。

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

- `TranslationAgent`（张睿桐）：可直接复用 `mercury.agent.provider`、`mercury.agent.prompts`、`SummaryWorker` 节流模式。
- `AgentRuntime`（共享 task queue）：当前 worker 直接挂在 `MainWindow`，未来抽到 `mercury.core.tasking` 后只需替换工厂。

## 10. Code Review（2026-06-04）

> 审查范围：`summary_agent.py`、`summary_worker.py`、`batch_worker.py`、`runtime_config.py`、`test_summary_agent.py`、`summary.default.yaml`
>
> 评审基于 Phase 2 完成时的代码状态。Phase 3 重构后这些文件位于 `mercury.agent.summary.*` 与 `mercury.resources.prompts` 下，模块内容与评审时一致，仅 import 路径变化。

### 10.1 架构与设计

整体分层清晰：`SummaryAgent` 作为纯逻辑层，不依赖 Qt，仅通过 `LLMProvider` Protocol 与具体 HTTP 实现解耦，做到了 GUI-free 的可测试性。`SummaryRequest` / `SummaryResult` 均使用 `frozen=True` 的 dataclass，保证了值语义的不可变性。三种调用模式（`run` / `stream` / `stream_iter`）覆盖了非流式、带回调的流式、以及原始迭代器三种消费场景，接口弹性不错。

`truncate_content` 的 60/40 头尾切片策略合理——文章导语和结尾结论通常信息密度最高，中间插入裁剪提示让模型知道内容被截断，这是一个经过思考的设计。模板指纹（`template_fingerprint`）用于标记持久化结果的版本，方便后续缓存失效判断，也是个好细节。

### 10.2 需要关注的问题

**（1）`run()` 缺少空响应校验**

`stream()` 在第 145-146 行对空响应做了 `SummaryAgentError` 防护，但 `run()` 只做了 `.strip()` 就直接返回了——如果 Provider 返回空白字符串，`run()` 会静默产出一个 `text=""` 的 `SummaryResult`。虽然 `batch_worker.py` 在 `_run_one` 里补做了空检查（第 128 行），但这条防线不在 Agent 层，意味着直接调 `agent.run()` 的其他代码路径拿不到保护。建议在 `run()` 中也加一道空响应检查，与 `stream()` 对齐。

**（2）`stream_iter()` 丢弃了 `truncated` 标记**

`stream_iter()` 在第 158 行用 `_` 忽略了 `_render()` 返回的 `truncated` 标记，仅 yield 原始 delta。这导致 `SummaryWorker` 无法得知内容是否被裁剪，最终 `finished` 信号不携带该信息，GUI 层也无法向用户展示裁剪提示。如果裁剪标记对用户体验有意义（文档第 8 节提到 `SummaryResult.truncated` 是有意设计的），那 `stream_iter` 这条路需要把它传出来。

**（3）`SummaryWorker` 手动拼装 `model_id`，与 `SummaryAgent._model_tag` 逻辑重复**

`summary_worker.py` 第 116 行自行拼接 `model_id`：
```python
model_id = f"{getattr(self._agent._provider, 'model', 'unknown')}@{self._agent.template.fingerprint}"
```
这段逻辑与 `SummaryAgent._model_tag()` 完全重复，且访问了 `_agent._provider`（私有属性）。如果未来 `_model_tag` 的格式发生变化，Worker 不会自动跟进。根本原因是 `stream_iter()` 不返回 `SummaryResult`，Worker 拿不到 agent 层产出的 `model_id`。建议要么让 `stream_iter` 返回一个 `(result_meta, iterator)` 的元组，要么在 `SummaryAgent` 上暴露一个公开的 `build_model_id()` 方法。

**（4）`_model_tag` 依赖鸭子类型获取 `model` 属性**

`LLMProvider` Protocol 只定义了 `complete()` 和 `stream()` 两个方法，并没有声明 `model` 属性。`_model_tag` 用 `getattr(self._provider, "model", "unknown")` 来获取，属于隐式契约。一旦换一个没有 `model` 属性的 Provider 实现，就会默默回退到 `"unknown"` 而不会报错。建议将 `model` 加入 `LLMProvider` Protocol 的定义（至少作为 `property`），或者在 `SummaryAgent.__init__` 时要求显式传入 `model_id`。

**（5）线程安全的取消标记**

`SummaryWorker._cancel_requested` 在 GUI 线程写、Worker 线程读，没有使用 `QMutex` 或 `threading.Event`。代码注释承认了这一点（"GIL makes this safe enough for MVP"），目前确实问题不大——最多多处理一个 token。但需要注意：如果未来迁移到 `asyncio` 或 C 扩展场景，这个假设就不再成立。建议至少用一个 `threading.Event` 替代裸 `bool`，成本很低且更规范。

**（6）`SummaryRequest` 的 `detail_level` 校验延迟到 `_render()` 阶段**

传入非法 `detail_level`（如 `"medium"`）时，`SummaryRequest` 构造成功，直到 `agent.run()` / `agent.stream()` 调 `_render()` 才抛 `SummaryAgentError`。这意味着一个无效的请求对象可以在系统中存在一段时间而不被发现。如果给 `SummaryRequest` 加一个 `__post_init__` 校验，可以在构造时就 fail-fast。不过需要注意这会让 dataclass 不再完全"平坦"，需要权衡。

### 10.3 测试覆盖

`test_summary_agent.py` 覆盖了核心路径：`run` 正常返回、`stream` 组装 chunk、空响应报错、非法 `detail_level` 报错、`ProviderError` 透传、`stream_iter` 原始迭代、以及 `target_language` 透传。`FakeProvider` 的设计简洁有效。

但有几处空白值得补充：

- **`truncate_content` 无直接测试**：作为 Phase 2 新增的功能，60/40 切片比例、边界情况（`max_chars=0`、`max_chars` 为负、文本刚好等于 `max_chars`、裁剪提示本身超过 `max_chars`）都应有独立的单元测试。
- **`run()` 对 `ProviderError` 的透传**：`test_provider_error_propagates` 只测了 `stream` 路径，`run()` 路径没有对应的测试。
- **`SummaryWorker` 无测试**：节流逻辑（80ms flush）、取消语义、`finished` vs `cancelled` 的竞态都没有测试覆盖。考虑到 Worker 依赖 Qt 信号，纯单测可能比较困难，但至少可以用 mock 信号做基本的行为验证。
- **`BatchSummaryWorker` 无测试**：串行执行、取消时的 skipped 计数、空内容跳过等逻辑均未测试。
- **`build_summary_result` 辅助函数**：解析 `model_id` 中的 `@` 分隔符，但无对应测试验证边界情况（如 `model_id` 不含 `@` 时的行为）。

### 10.4 小问题与风格

- `run()` 中第 106-107 行的 `except ProviderError: raise` 在语义上等价于不写（异常本来就会自动向上传播），但它确实起到了"显式声明意图"的作用，可以接受。
- `runtime_config.py` 的 `_SettingsLike` Protocol 是一个轻量级的结构子类型，避免了硬依赖具体的 `SettingsStore` 类，设计合理。
- `batch_worker.py` 对空内容做了前置拦截（第 96-103 行），但 `summary_agent.py` 本身不做这个检查。如果 Agent 会被其他入口直接调用（不经过 Worker），建议在 Agent 层也加上空内容防护。

### 10.5 总结

Summary Agent 的整体实现质量不错，架构分层合理，核心抽象（`LLMProvider` Protocol、`PromptTemplate`、`SummaryRequest/Result`）设计干净，具备良好的可测试性和可扩展性。主要改进方向集中在：补齐 `run()` 与 `stream()` 在空响应校验上的一致性、解决 `stream_iter` 路径丢失 `truncated` 标记和 `model_id` 重复拼装的问题、将 `model` 属性纳入 Provider 契约、以及补充 `truncate_content` 和 Worker 层的测试覆盖。这些问题大多不影响当前 MVP 的正确性，但在进入生产阶段前建议逐一处理。

### 10.6 修复跟进（2026-06-04 当日）

逐条对照 §10.2 / §10.3 的发现已落地：

| 编号 | 问题 | 处理 |
|---|---|---|
| 10.2(1) | `run()` 缺少空响应校验 | `run()` 与 `stream()` 一致：空 / 全空白响应抛 `SummaryAgentError`。新测试 `test_run_rejects_empty_provider_response` 守门 |
| 10.2(2) | `stream_iter` 丢弃 `truncated` 标记 | 新增 `prepare_stream(request) -> (StreamMeta, iterator)`，`StreamMeta` 携带 `model_id` / `template_fingerprint` / `truncated`；`stream_iter` 保留为兼容层 |
| 10.2(3) | Worker 重复拼装 `model_id`、访问 `_provider` 私有属性 | `SummaryAgent.build_model_id()` 公开，`SummaryWorker` 改走 `prepare_stream` 直接拿到 `meta.model_id` |
| 10.2(4) | `model` 属性是隐式契约 | `LLMProvider` Protocol 显式声明 `model: str`；`SummaryAgent.provider_model` 直接读取，去掉 "unknown" 默默回退 |
| 10.2(5) | `_cancel_requested` 是裸 `bool` | 改为 `threading.Event`，`SummaryWorker` 与 `BatchSummaryWorker` 都换上 |
| 10.2(6) | `detail_level` 校验延迟到 `_render` | `SummaryRequest.__post_init__` 在构造时即校验 `detail_level` 与 `max_content_chars`，fail-fast |
| 10.3 | `run()` 路径无 `ProviderError` 测试 | 新增 `test_provider_error_propagates_in_run` |
| 10.3 | `truncate_content` 无独立测试 | 已存在 `tests/test_summary_truncation.py`（Phase 2 加），覆盖 0 / 负 / 正常 / 极长四种边界 |
| 10.3 | `SummaryWorker` 无测试 | 新增 `tests/test_summary_worker.py` —— started/token/finished 顺序、节流、`truncated` 透传、`ProviderError` → failed、cancel → cancelled、空响应 → failed |
| 10.3 | `BatchSummaryWorker` 无测试 | 已存在 `tests/test_batch_summary.py`（Phase 2 加） |
| 10.3 | `build_summary_result` 无 `@` 边界测试 | 现行为：缺 `@` 时 `template_fingerprint` 为空（不再继承全串）；新增三个 case |
| 10.4 | Agent 层无空内容拦截 | 由 `SummaryRequest.__post_init__` 之外的入口仍可空内容；当前由 Agent 在 `run()` / `stream()` 完成后判空。批量入口的前置拦截保留 |

GUI 层一并跟进：`SummaryWorker.finished` 现在多带 `truncated: bool`，`mercury.gui._on_summary_finished` 接收并把状态条前缀 `[已裁剪]` 显示给用户。

回归测试：127 全过（Phase 3 重构后基线 112 + 本轮 9 新增 worker 单测 + 6 新增 agent / prepare_stream 测试）。
