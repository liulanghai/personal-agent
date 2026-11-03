# S0 · 工程地基

| 项目 | 内容 |
| --- | --- |
| 状态 | ② 业界调研 |
| 关联 | 路线图 S0 |
| 开始日期 | 2026-11-03 |

## 关卡记录

| 关卡 | 日期 | 结论 | 备注 |
| --- | --- | --- | --- |
| G1 需求确认 | 2026-11-03 | 通过 | 采纳草案目标/非目标/验收标准；5 个待讨论问题按下方「G1 决议」 |
| G2 调研讨论 | | | |
| G3 方案确认 | | | |

已确认的前置决策（2026-11-03）：S0 先于所有新功能；Python 升级到 3.12；主题按 S0 → S1 → S2 → S3 顺序推进；每个主题一份文档。

---

## ① 需求定义

### 背景与问题

现有代码功能完整，但不适合长期迭代与作为学习材料：

- 代码密度过高：最长单行约 2800 字符，`frontend/src/main.tsx` 191 行中有 25 行超过 150 字符。
- 无 lint/格式化/类型检查配置，无 CI，`main` 可直接推送。
- `runtime.py` 中 Agent 循环与 Chat Completions HTTP 细节耦合，无法接入其他协议（如 Anthropic Messages）或在测试中替换 provider。
- Python 3.9 已停止维护。
- 测试只有集成层，无契约一致性检查。

### 目标（草案）

- 升级 Python 3.12，依赖管理切换到 uv。
- 后端按职责拆分模块（api / runtime / providers / tools / context / store），**行为不变**。
- 引入 Provider 抽象：Runtime 只依赖统一的流式接口；首个实现为现有 OpenAI Chat Completions 兼容协议。
- 工具链：ruff、mypy、ESLint、Prettier、pre-commit；`make check` 一条命令完成全部检查。
- GitHub Actions CI：PR 上运行 `make check`；开启 `main` 分支保护。
- 契约检查：CI 验证 `docs/openapi.json` 与 `sdk/src/schema.d.ts` 与源码一致。
- 前端拆分组件与 hooks，补最基础的前端测试。

### 非目标（草案）

- 不新增产品功能，不改变 API 行为（除非为修复明显问题，需单独讨论）。
- 不在 S0 实现 Anthropic 协议 provider（可作为抽象的验证，在 S1 讨论）。
- 不做 Agent 评测（S2）、不改上下文策略（S3）。

### 用户场景

1. 作为开发者，我在 PR 上看到 CI 自动给出 lint、类型、测试、契约检查结果。
2. 作为学习者，我能顺着模块目录读懂一次 Run 从 HTTP 请求到模型调用再到工具执行的全过程。
3. 作为 AI 协作者（Codex/Claude），能用 `make check` 自证改动正确。

### 验收标准（草案）

- [ ] Python 3.12 环境下全部现有测试通过，验收主线手工复测通过。
- [ ] `make check` 通过，且在 GitHub Actions 中运行。
- [ ] `main` 分支保护已开启，需 PR 且 CI 通过。
- [ ] Runtime 不直接引用 httpx；Provider 可在测试中注入替换。
- [ ] 无超过 100 字符的 Python 行（ruff 强制）。
- [ ] 文档（README、architecture、AGENTS.md 中的命令）同步更新。

### 学习目标（草案）

- 理解一个 Agent 项目的分层：哪些是"Agent 特有"的（循环、provider、工具、上下文），哪些是通用后端工程。
- 理解 Provider 抽象应该抽象到什么程度：流式增量、工具调用、用量、错误分类。
- 熟悉 Python 现代工具链（uv、ruff、mypy）与 CI 实践。

### G1 决议（2026-11-03）

1. 依赖管理切换到 **uv**（含 Python 版本管理与 `uv.lock`）。
2. 类型检查使用 **mypy**。
3. Provider 抽象在 S0 **最小抽离**：Runtime 依赖统一流式接口；完整接口设计在 S1 结合调研讨论。
4. 前端在 S0 只做**组件拆分 + ESLint/Prettier + 冒烟测试**。
5. 实现拆为 4 个 PR：工具链 + CI → 后端模块拆分 → Provider 抽象 → 前端拆分。

（以上为方向性决议，具体配置在 ③ 技术方案中细化并经 G3 确认。）

---

## ② 业界调研

查阅日期：2026-11-03。方法：浅克隆源码阅读，未执行任何第三方代码。关键结论已抽查（CLAUDE.md 软链接、测试禁用真实模型、`exclude-newer`、codex 移除 Chat 协议）。

### 参考对象

| 项目 | 版本/提交 | 关注点 |
| --- | --- | --- |
| [openai/openai-agents-python](https://github.com/openai/openai-agents-python) | `e355d69`（2026-10-30） | 工程骨架、`Model` 接口、`ScriptedModel` |
| [pydantic/pydantic-ai](https://github.com/pydantic/pydantic-ai) | `a56a6d6`（2026-11-03） | 工具链严格度、`Model`/`StreamedResponse`、VCR 测试 |
| [openai/codex](https://github.com/openai/codex) | `7e8143a`（2026-11-03） | 契约生成一致性检查、`ResponseEvent`、重试位置 |
| [huggingface/smolagents](https://github.com/huggingface/smolagents) | `96f33fa`（2026-10-06） | 轻量对照组 |

### A. 工程骨架对比

| | agents-python | pydantic-ai | codex | smolagents |
| --- | --- | --- | --- | --- |
| uv + 锁文件 | 是，CI `UV_FROZEN=1` | 是，CI `uv lock --check` | SDK 用 uv；另有 Cargo/pnpm 锁 | 无锁文件 |
| Python 下限 / CI 矩阵 | 3.10 / 3.10–3.14 | 3.11 / 3.11–3.15 | SDK 3.10 | 3.10 / 3.10、3.12 |
| ruff 行宽 / 规则 | 100 / `E,W,F,I,B,C4,ASYNC,UP` | 120 / 较多，含 `D`、复杂度 15 | 100 / `E,F,I,B,C4` | 119 / `E,F,I,W` |
| 类型检查 | mypy strict（部分放宽）+ pyright basic | pyright strict + mypy strict | Python SDK 无 | 无 |
| 统一入口 | `make check` | `make all` | `just` | `make quality` |
| pre-commit | 无 | 完整（含 `no-commit-to-branch`、zizmor） | 无 | 简单 |
| 覆盖率门槛 | 85% | 100% | 未核实 | 无 |
| 生成物一致性 | 已发布 API 契约对比脚本 | 锁文件检查 | schema 快照测试 + CI `git status --porcelain` 必须为空 | 无 |
| `CLAUDE.md` | 软链接 → `AGENTS.md` | 软链接 → `AGENTS.md`，另有目录级 AGENTS.md | 根目录无，仅子目录级 | 4 行 AGENTS.md |
| 依赖冷却 | `exclude-newer = "7 days"` | `exclude-newer = "7 days"` | — | — |

关键位置：agents-python `Makefile`、`.github/workflows/tests.yml`；pydantic-ai `.pre-commit-config.yaml`、`.github/workflows/ci.yml`；codex `.github/actions/check-clean-worktree`、`sdk/python/tests/test_contract_generation.py`。

### B. 测试如何对待真实模型

| | 防误调用机制 | 替身 | 真实模型测试 |
| --- | --- | --- | --- |
| agents-python | `tests/conftest.py:136` monkeypatch 后 `pytest.fail("Real models should not be used in tests!")`；CI 假 key | `src/agents/testing/model.py` `ScriptedModel`（随包发布） | 独立 `integration_tests/`，需专用服务账号 |
| pydantic-ai | `tests/conftest.py:108` `ALLOW_MODEL_REQUESTS = False` | `TestModel`、`FunctionModel`；默认写法 VCR 录制回放 + inline-snapshot | `*_live` 标记隔离 |
| codex | — | wiremock 回放 SSE（`core/tests/common/responses.rs`）+ insta 快照 | 未核实 |
| smolagents | — | 手写 `FakeToolCallModel` 等 | — |

结论：**默认禁止真实调用、显式开启并隔离运行**是共识；分歧在替身注入层次——模型对象层（agents-python、pydantic-ai）或 HTTP 层（codex，与本项目现状相同）。

### C. Provider 抽象对比

| | agents-python | pydantic-ai | codex-rs |
| --- | --- | --- | --- |
| 接口 | `Model.get_response` / `stream_response`（`models/interface.py`） | `Model.request` / `request_stream`（`models/__init__.py`） | `ModelClientSession::stream`（`core/src/client.rs`） |
| 内部消息格式 | OpenAI Responses items | 中立 `ModelMessage`，各实现 `_map_messages` | `ResponseItem`（即线上格式） |
| 流事件 | 沿用 Responses 事件；Chat 实现翻译为 Responses 事件 | `PartStart/Delta/End`；delta 分 Text/Thinking/ToolCall | 自定义枚举 `ResponseEvent` |
| 工具参数拼接 | provider 内缓冲，`finish_reason=tool_calls` 时吐出 | 模型层共享 `_parts_manager` | 忽略 delta，用服务端 done item |
| 错误 | provider 给 `get_retry_advice()`，runner 决定 | 细分异常（限流、配额、上下文超限、鉴权…） | 错误枚举 + `retry_delay()`，`None` 即不可重试 |
| 重试位置 | runner（需开启），并关闭 SDK 自带重试 | SDK/transport | turn 循环 |
| 用量 | `Usage`，流式需 `stream_options` | `RequestUsage`（含缓存 token），未报告记为 unmeasured | `Completed.token_usage` |

值得注意：codex 已移除 Chat Completions 支持（`model-provider-info/src/lib.rs:109`，配置 `wire_api="chat"` 直接报错）。是否代表行业向 Responses 风格收敛属**推测**；对本项目的含义是内部格式应保持中立，不绑死 Chat 协议。

### 对本项目的启发（AI 建议，待 G2 讨论）

| 借鉴 | 不借鉴 | 暂缓 |
| --- | --- | --- |
| `make check` 唯一入口，CI 调用同一目标 | 按改动分流 CI、alls-green 汇总 job（单人项目过度设计） | VCR 录制回放（S1 接入第二个协议时） |
| CI 重新生成 OpenAPI/SDK 后检查工作区干净 | 100% 覆盖率门槛 | 细分异常类、retry-after（S1） |
| 测试默认禁止真实模型（conftest 拦截）+ CI 假 key | pyright + mypy 双检查 | reasoning / 工具参数流式事件（S1） |
| `ScriptedProvider` 测试替身，注入在 Provider 层 | Bazel/Nix 等重型构建 | 用量中的缓存 token、ProviderRegistry（S1/S2） |
| uv `--frozen` + `uv lock --check` + `exclude-newer = "7 days"` | 内部格式直接用某家线上格式 | inline-snapshot 快照测试（视需要） |
| ruff 行宽 100、规则 `E,W,F,I,B,C4,ASYNC,UP` | | 覆盖率门槛（先观察基线再定） |
| 轻量 pre-commit：ruff、check-yaml/toml、大文件 | | |
| 最小 Provider：`stream()` + `TextDelta`/`ToolCall`(完整参数)/`Usage`/`Finish`，失败抛 `ProviderError(kind, retryable)` | | |
| 中立内部消息格式，由 provider 负责转换 | | |
| GitHub Actions 锁定到完整 SHA | | |

### G2 待讨论

1. `CLAUDE.md` 用软链接（与业界一致、两工具内容完全相同）还是保留 `@AGENTS.md` 导入（可写 Claude 专有补充）？
2. mypy 严格度：一开始就 `strict = true` 全量，还是新模块 strict、旧代码按模块放宽逐步收紧？
3. 覆盖率：只统计不设门槛，还是先设一个基线（如 80%）？
4. 测试替身层次：Provider 层 `ScriptedProvider` 为主，保留少量 HTTP 层测试覆盖 Chat 协议解析——是否认同？
5. 错误处理：Error 作为异常抛出（pydantic-ai/codex 风格）还是作为流事件 yield？

## ③ 技术方案

（G2 后开始）

## ④ 实现记录

## ⑤ 验证与评测

## ⑥ 学习总结（用户执笔）
