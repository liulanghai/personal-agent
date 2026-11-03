# S0 · 工程地基

| 项目 | 内容 |
| --- | --- |
| 状态 | ④ 实现 |
| 关联 | 路线图 S0 |
| 开始日期 | 2026-11-03 |

## 关卡记录

| 关卡 | 日期 | 结论 | 备注 |
| --- | --- | --- | --- |
| G1 需求确认 | 2026-11-03 | 通过 | 采纳草案目标/非目标/验收标准；5 个待讨论问题按下方「G1 决议」 |
| G2 调研讨论 | 2026-11-03 | 通过 | 采纳「启发」表；CLAUDE.md 保留导入；mypy 新模块 strict、旧代码按模块放宽；覆盖率只统计；替身以 ScriptedProvider 为主 + 少量 HTTP 层协议测试；错误抛异常 |
| G3 方案确认 | 2026-11-03 | 通过 | 5 项待确认全部同意；仓库将改为公开，以便启用分支保护 |

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

### 总原则

- **行为不变**：S0 不改 API、事件、数据库结构、提示词与模型请求内容。证据：现有测试全部通过 + `docs/openapi.json` 零差异（由 `make check-gen` 强制）。
- 4 个 PR 顺序合入，每个 PR 合入后 `make check` 与验收主线都可用。
- 纯格式化（ruff format / prettier）作为 PR 内单独提交，便于评审；该类提交不计入 400 行建议。

### PR1 · 工具链 + CI

**Python 环境（uv）**

- `pyproject.toml`：`requires-python = ">=3.12"`；开发依赖放 `[dependency-groups] dev`（pytest、ruff、mypy、types-PyYAML、types-jsonschema、pre-commit）。
- `[tool.uv] exclude-newer = "7 days"`；新增 `.python-version`（3.12）与 `uv.lock`，删除 `requirements.lock`。
- 首次锁定**沿用 requirements.lock 中的现有版本**（3.12 不再需要的 backport 包除外），依赖升级另开 `chore` PR，避免与升级 Python 混在一起难以定位问题。
- `uv sync` 仍生成 `.venv/`，`scripts/start.command` 与 README 启动命令无需改变。

**静态检查**

- ruff：`line-length = 100`，`select = ["E","W","F","I","B","C4","ASYNC","UP"]`，`target-version = "py312"`。
- mypy：全局 `strict = true`、`warn_unused_ignores = true`；现有模块列入 `[[tool.mypy.overrides]]` 放宽（`disallow_untyped_defs = false` 等）。**规则：PR2/PR3 重写到哪个模块，就从放宽名单中移除哪个**，S0 结束时名单为空或仅剩说明了原因的条目。

**统一入口 `Makefile`**

| 目标 | 内容 |
| --- | --- |
| `make install` | `uv sync --frozen` + `npm ci` |
| `make fmt` | `ruff format` + `ruff check --fix`（PR4 起加 prettier） |
| `make lint` | `ruff check` + `ruff format --check`（PR4 起加 eslint、prettier --check） |
| `make typecheck` | `mypy backend` + `tsc --noEmit` |
| `make test` | `pytest`（含覆盖率统计，不设门槛；PR4 起加 vitest） |
| `make gen` | 导出 OpenAPI + 生成 SDK 类型（即现 `npm run sdk:generate`） |
| `make check-gen` | `make gen` 后 `git diff --exit-code docs/openapi.json sdk/src/schema.d.ts` |
| `make check` | `lint typecheck test check-gen` |
| `make build` | 前端生产构建 |

**测试默认禁止真实网络**

`tests/conftest.py` 增加 autouse fixture：把 `httpx.AsyncHTTPTransport.handle_async_request` 替换为直接 `pytest.fail("Real network/model calls are not allowed in tests")`。`MockTransport` 不经过该类，现有测试不受影响；任何意外的真实请求立即失败。这一层与 Provider 无关，PR3 之后依然有效。（agents-python 在模型层拦截，我们在传输层拦截，覆盖面更广。）

**pre-commit（轻量）**

- 本地 hooks 调用 `uv run --frozen ruff …`，**与 uv.lock 同版本**，避免 pre-commit 自带 ruff 版本漂移。
- 通用 hooks：check-yaml、check-toml、check-added-large-files、detect-private-key、end-of-file-fixer、trailing-whitespace。

**CI（`.github/workflows/ci.yml`）**

- 触发：`pull_request`、`push` 到 `main`；`permissions: contents: read`；同一分支新提交取消旧运行（concurrency）。
- 单 job（ubuntu-latest，Python 3.12，Node 22）：checkout → setup-uv（启用缓存）→ setup-node（npm 缓存）→ `uv lock --check` → `make install` → `make check` → `make build`。
- 所有 action 锁定到完整 commit SHA（实现时查最新发布版本的 SHA）。
- 不做 Python 版本矩阵：本项目是应用而非库，只支持一个版本。

**分支保护**

- 要求 PR、要求 CI 通过、禁止强推。需在 GitHub 网页设置（本机未安装 `gh`）。
- 风险：GitHub 免费账户的**私有仓库**不支持分支保护规则；若仓库为私有，需改用 pre-commit 的 `no-commit-to-branch` 作为本地兜底。实现前确认仓库可见性。

**文档**：README 开发环境改为 uv；`AGENTS.md`、`docs/testing.md` 中的命令改为 `make check`。

### PR2 · 后端模块拆分（纯重构）

目标结构：

```
backend/agent/
  app.py              create_app：只做组装（配置、存储、工具、Runtime、路由、静态文件）
  config.py           Settings 读取/保存/校验（settings.json、环境变量、密钥保护规则）
  security.py         Origin / Host / Bearer 中间件
  store.py            SQLite；所有 SQL 只出现在这里，对外提供具名方法与 TypedDict 行类型
  api/
    errors.py         统一错误格式
    schemas.py        请求/响应模型（含现 app.py 中的 Input 模型）
    routes/           conversations.py · runs.py · files.py · settings.py · skills.py（APIRouter）
  runtime/
    runtime.py        Run 生命周期：launch / execute / cancel / 启动时中断恢复
    loop.py           Agent 循环（PR2 暂保留 httpx，PR3 替换为 Provider）
  tools/
    registry.py       工具定义、参数校验、分发
    paths.py          工作空间边界（唯一的路径校验实现）
    files.py          list / read / search / write
    skills.py         list_skills / read_skill / read_skill_resource
  context/
    builder.py        ContextBuilder
    discovery.py      规则与 Skill 发现
```

- 路由内不再出现 SQL 字符串（如 `require(table, id)` 拼接表名改为具名方法）。
- 删除未被调用的 `Runtime.text`。
- 不处理 async 中的阻塞文件 IO（非目标，记入遗留问题）。
- 测试只允许修改 import / monkeypatch 路径，不改断言；OpenAPI 零差异。

### PR3 · Provider 最小抽象

```
backend/agent/providers/
  base.py          中立类型与 Provider 协议
  openai_chat.py   OpenAIChatProvider：消息映射、SSE 解析、工具参数拼接、错误分类
tests/support/
  scripted_provider.py   ScriptedProvider：按步骤 yield 事件的测试替身
```

接口（最终签名在实现 PR 中评审）：

```python
@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: str          # 已拼接完整的原始 JSON 字符串，不在 provider 内解析

@dataclass(frozen=True)
class Message:              # 中立内部格式
    role: Literal["system", "user", "assistant", "tool"]
    content: str | None = None
    tool_calls: tuple[ToolCall, ...] = ()
    tool_call_id: str | None = None

@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]

@dataclass(frozen=True)
class TextDelta:
    text: str

@dataclass(frozen=True)
class Usage:
    input_tokens: int
    output_tokens: int

@dataclass(frozen=True)
class Finish:
    reason: Literal["stop", "tool_calls", "length", "content_filter", "other"]

StreamEvent = TextDelta | ToolCall | Usage | Finish

class ProviderError(Exception):
    kind: Literal["auth", "rate_limit", "context_length", "bad_request", "server", "network", "other"]
    retryable: bool

class Provider(Protocol):
    def stream(self, messages: Sequence[Message], tools: Sequence[ToolSpec], *,
               model: str) -> AsyncIterator[StreamEvent]: ...
```

职责划分：

| 归 Provider | 归 Runtime（loop.py） |
| --- | --- |
| 中立 Message ↔ Chat Completions 消息映射 | 循环与步数上限 |
| SSE 解析、`[DONE]`、空 choices | 收到 `TextDelta` 写 `message.delta` 事件 |
| 按 index 缓冲并拼接工具参数，流结束时按 index 顺序交出完整 `ToolCall` | 收到 `ToolCall` 后 `json.loads`；非法 JSON 作为工具错误回给模型（现有行为） |
| HTTP 状态码 / 网络异常 → `ProviderError(kind, retryable)` | 捕获 `ProviderError` → Run 失败，错误信息与现在一致 |
| 不持久化、不记录 provider 响应体（保持现有安全约束） | 工具执行、事件写入、历史追加 |

- Runtime 通过构造参数 `provider_factory: Callable[[Settings], Provider]` 获得 Provider；`create_app(data_dir, provider_factory=None)` 默认使用 `OpenAIChatProvider`，测试注入 `ScriptedProvider`。任务开始时读配置、执行中不切换 provider 的规则不变。
- **S0 不加重试**：`retryable` 只分类、不使用；重试属于 S1「错误恢复」主题。
- **S0 不发送 `stream_options.include_usage`**：避免改变请求、不兼容部分兼容端点；返回中若含 usage 则解析为 `Usage` 事件，Runtime 暂不持久化（S2 处理）。
- ContextBuilder 输出改为 `list[Message]`。

测试：

- `tests/providers/test_openai_chat.py`：真实格式的 SSE 样本——参数分多块到达、两个调用交错到达、仅文本、含 usage 的末块、空 choices、缺少 `[DONE]`、401/429/500/网络错误分类、非 JSON 参数原样交出。
- API 集成测试改用 `ScriptedProvider`，删除拆 prompt 取附件列表的写法（附件改由 ScriptedProvider 记录收到的 messages 后断言）。
- 保留 1～2 个经 `OpenAIChatProvider` + `MockTransport` 的端到端测试，覆盖 HTTP 层。

### PR4 · 前端拆分

- ESLint（flat config：typescript-eslint、react-hooks）+ Prettier；先单独提交全量格式化（含 `style.css` 现为单行 14KB）。
- `main.tsx` 按职责拆分（具体切分在实现时阅读后于 PR 中说明）：

```
frontend/src/
  main.tsx            挂载入口
  App.tsx             布局与路由级状态
  api/client.ts       AgentClient 单例
  hooks/              useConversations · useRunEvents · useSettings …
  components/         Sidebar · ChatView · MessageList · Composer · RunDetails · SettingsPanel · SkillsPanel · ArtifactPreview …
  lib/events.ts       SSE 事件 → UI 状态的纯函数（可单测）
```

- 冒烟测试（Vitest + Testing Library + jsdom）：App 在 mock SDK 下可渲染；`lib/events.ts` 的事件归并纯函数单测。
- 不改视觉与交互；手工复测验收主线。

### 安全影响

- 不放宽任何权限边界；工作空间路径校验集中到 `tools/paths.py`，现有越界与符号链接测试保留。
- 测试新增真实网络拦截；CI 无任何密钥，`permissions: contents: read`；action 锁定 SHA。
- detect-private-key hook 防止误提交密钥。

### 测试计划

- 每个 PR：`make check` 通过（CI）；OpenAPI 零差异。
- PR3 新增 Provider 单元测试（见上）。
- PR4 新增前端冒烟测试。
- S0 结束：Python 3.12 下手工复测验收主线，真实模型发起一次周报任务，记录于 ⑤。

### PR 拆分

1. `chore(s0): uv + python 3.12 + ruff/mypy + pre-commit + CI + make check`
2. `refactor(s0): split backend into api/runtime/tools/context modules`
3. `refactor(s0): introduce minimal provider abstraction`
4. `refactor(s0): split frontend, add eslint/prettier and smoke tests`

### G3 决议（2026-11-03，均已同意）

1. S0 不加重试、不发送 `stream_options`（保持行为不变，重试归 S1）。
2. `ScriptedProvider` 放在 `tests/support/`，不随应用包发布（agents-python 随包发布是因为它是库）。
3. PR2 顺带把所有 SQL 收进 `store.py`（略超"纯拆分"，但路由层不再有 SQL）。
4. 首次 uv 锁定沿用现有依赖版本，依赖升级另开 PR。
5. 仓库当前为私有，将改为公开以启用分支保护；公开前扫描 Git 历史确认无密钥。

## ④ 实现记录

| PR | 分支 | 内容 | 状态 |
| --- | --- | --- | --- |
| PR1 | #3 | uv + Python 3.12、ruff/mypy、pre-commit、`make check`、CI、测试网络拦截 | 已合并 2026-11-03 |
| PR2 | #4 | 后端模块拆分 | 已合并 2026-11-03 |
| PR3 | `refactor/s0-provider` | Provider 最小抽象 | 评审中 |
| PR4 | | 前端拆分 | 未开始 |

PR1 实现说明与偏离：

- 首次锁定通过临时 `constraint-dependencies` 固定为原 `requirements.lock` 版本后移除约束，运行时依赖版本不变（fastapi 0.128.8、httpx 0.28.1、pydantic 2.13.5…）。
- ruff 剩余问题的处理：`B904` 在 4 处 `raise HTTPException(...)` 后加 `from None`（不改变响应）；长字符串拆为隐式拼接，**系统提示词经 AST 校验字节一致**（sha256 前缀 `e14aaab540bd4543`）；建表 SQL 换行，语义不变；FastAPI 的 `File`/`Header` 默认参数通过 `extend-immutable-calls` 允许。
- mypy 旧模块放宽名单：`app`、`context`、`discovery`、`runtime`、`store`、`tools`；仅补了 6 处局部变量注解以通过 `check_untyped_defs`。
- 删除误提交的编辑器交换文件 `docs/features/.s0-foundation.md.swp`，`.gitignore` 增加 `*.swp`、缓存与 `*.egg-info/`。
- `npm run sdk:generate` 保留为 `make gen` 的别名。
- 附带发现（未处理，记入遗留）：`tools.py` 覆盖率 70%，`search_files` 分支无测试。

PR2 实现说明与偏离：

- 按 ③ 的目标结构拆分；文件用 `git mv` 移动以保留历史（`schemas.py → api/schemas.py`、`context.py → context/builder.py`、`discovery.py → context/discovery.py`）。
- 在 ③ 结构之外新增三个小模块：`api/deps.py`（`Services` 容器 + `require_conversation/run/file`，替代拼接表名的 `require(table, id)`）、`api/routes/system.py`（health，避免放进无关路由）、以及 `store.RunConflictError`（让 SQLite 异常不越过存储层）。
- `store.py`：SQL 全部收拢为具名方法（`create_run`、`list_runs`、`latest_event_data` 等），返回 TypedDict；`runs.file_ids` 在存储层解码为 `list[str]`，原 `public_run` 删除。`Store.execute` 保留为公开方法，仅供测试插入原始行。
- `tools/paths.py` 成为唯一的路径校验实现：工作空间、`reports/` 写入限制、Skill 资源目录三处都经由它。
- `tools/__init__.py`、`context/__init__.py` 不做再导出，避免 `context.discovery → tools.paths` 与 `tools.registry → context.discovery` 形成导入环。
- 删除未调用的 `Runtime.text`；取消逻辑从路由移入 `Runtime.cancel`，启动恢复/关闭移入 `Runtime.recover_interrupted/shutdown`。
- mypy 放宽名单已**清空**（`pyproject.toml` 中整段删除），全部 27 个源文件通过 strict。
- 测试改动仅限路径：`agent.runtime.httpx.AsyncClient → agent.runtime.loop.httpx.AsyncClient`，`agent.context / agent.tools` 的 import 改为子模块；断言未改。新增 `tests/test_tools.py`（5 项）：`search_files` 大小写不敏感的字面匹配与行号、跳过非 UTF-8/超限文件/符号链接、50 条上限与 400 字截断、空查询被 schema 拒绝；`read_file` 超限。
- **OpenAPI 与 SDK 有顺序差异、无语义差异**：路由按模块注册后 `/api/v1/discovery` 在 paths 中的位置从 `/runs/{rid}/context` 之后移到 `/runs/{rid}/events` 之后。已验证：新旧 `openapi.json` 解析后 `==` 为真；两份生成文件新旧版本的行集合（排序后）完全相同。按 `check-gen` 规则提交重新生成的文件。与 ③ 中"OpenAPI 零差异"的表述有出入，在 PR 中说明。

PR3 实现说明与偏离：

- 按 ③ 新增 `providers/base.py`、`providers/openai_chat.py`、`tests/support/scripted_provider.py`；`loop.py` 不再 import httpx。
- **`Provider` 协议比 ③ 多一个 `aclose()`**：`httpx.AsyncClient` 由 Provider 持有，Run 结束时在 `finally` 中关闭，避免连接泄漏。
- **`stream()` 返回 `AsyncGenerator` 而非 `AsyncIterator`**：Runtime 用 `contextlib.aclosing` 包裹，取消或异常时确定性地关闭底层 HTTP 流。
- `OpenAIChatProvider` 增加可选 `transport` 构造参数，仅用于测试注入 `MockTransport`；生产路径经 `from_settings(settings)` 创建。
- 错误信息保持原文：HTTP ≥ 400 为"模型服务返回 HTTP {code}，请检查设置、模型权限或额度"；网络异常为"执行失败（{异常类名}），请检查模型连接或本地文件"。分类只读取响应体前 4096 字节用于识别 `context_length_exceeded`，响应体不进入错误消息、事件或日志。新增 408 → `network`（可重试）。
- 行为保持：不跟随重定向（307 不报错、无内容，与重构前一致，由循环报"模型没有返回可显示的内容"）；非法工具参数 JSON 仍回给模型；不发送 `stream_options`；不重试；Usage / Finish 不持久化。
- `pyproject.toml` 的 pytest `pythonpath` 增加 `tests`，以便 `from support.scripted_provider import ...`。
- 测试：API 集成测试改用 `ScriptedProviderFactory`，假模型根据工具结果反应，不再拆 prompt；附件路径改为断言 ScriptedProvider 收到的 system 消息。保留 2 个 `OpenAIChatProvider + MockTransport` 端到端用例（流式 + 工具执行、401 失败且不泄露响应体）。新增 `tests/providers/test_openai_chat.py`（③ 列出的全部样本 + 请求结构、重定向）与 `tests/test_loop.py`（非法参数、工具失败、多步文本拼接、步数上限、空回合、ProviderError 转为 Run 失败且关闭 Provider）。

## ⑤ 验证与评测

PR1（2026-11-03，本机 macOS，Python 3.12.14、Node 22.22.0）：

- `make check` 退出码 0：ruff、ruff format、mypy（8 个源文件无错误）、tsc、pytest 20 项通过（新增网络拦截守卫测试）、契约一致性通过。
- 契约检查反例：临时修改 API 标题后 `make check-gen` 失败（退出码 2），还原后通过。
- `make build` 通过。`pre-commit run --all-files` 通过（首次运行修复了 TEMPLATE.md 行尾空格）。
- 覆盖率基线：总计 88%（app 88%、discovery 89%、runtime 86%、tools 70%）。
- GitHub Actions 首次运行通过（27s）。仓库设置：`main` 必需检查 `check`（strict）、仅 squash、合并后删除分支。
- 未验证：Python 3.12 下的浏览器验收主线手工复测（留待 S0 结束时统一进行）。

PR2（2026-11-03，本机）：

- `make check` 退出码 0：ruff、ruff format、mypy strict（27 个源文件、无放宽名单）、tsc、pytest 25 项通过（原 20 项断言未改 + 新增 5 项）、契约一致性通过。`make build` 通过。
- 覆盖率总计 88% → 93%；工具层原 `tools.py` 70% → `tools/files.py` 100%、`tools/registry.py` 94%。
- 路由与 Runtime 中无 SQL：`grep -rE "SELECT|INSERT|UPDATE |DELETE "` 除 `store.py` 外无结果。
- 真实进程冒烟：`uvicorn agent.app:create_app --factory` 启动，`/api/v1/health` 返回 ok，`/api/v1/settings` 字段不变，恶意 Origin 返回 403。
- 未验证：浏览器验收主线（仍留待 S0 结束时统一进行）。

PR3（2026-11-03，本机）：

- `make check` 退出码 0：ruff、ruff format、mypy strict、tsc、pytest 52 项通过、契约一致性通过（OpenAPI / SDK 无变化）。
- 覆盖率总计 93% → 94%；`providers/openai_chat.py` 95%，`runtime/loop.py` 100%。
- 测试中不存在真实网络调用（conftest 传输层拦截仍生效）；`sk-test-leak` 样本在错误消息与 Run 事件中均不出现。
- 未验证：真实模型下的周报主线（留待 S0 结束时统一进行）。

## ⑥ 学习总结（用户执笔）
