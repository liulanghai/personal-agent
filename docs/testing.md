# 测试策略

Agent 系统同时包含**确定性代码**（工具、存储、协议解析）和**非确定性行为**（模型决策）。前者用传统测试保证正确性，后者用评测（eval）衡量质量。两者都要有，但运行方式不同。

## 测试分层

| 层级 | 覆盖内容 | 模型 | 运行时机 | 状态 |
| --- | --- | --- | --- | --- |
| 单元测试 | 工具、路径边界、规则/Skill 发现、上下文构建、Provider SSE 解析与错误分类、Agent 循环、配置 | 无 / ScriptedProvider | 每个 PR（CI） | 部分已有 |
| 集成测试 | HTTP API + Runtime 循环 + SQLite，脚本化假模型驱动多步工具调用 | ScriptedProvider；HTTP 层用 MockTransport | 每个 PR（CI） | 已有 |
| 契约测试 | OpenAPI 与已提交版本一致；SDK 生成物一致；破坏性变更检测 | 无 | 每个 PR（CI） | S0 |
| 录制回放 | 录制真实 provider 的流式响应（脱敏），回放验证解析兼容 | 录制数据 | 每个 PR（CI） | S0/S1 |
| 安全测试 | 路径越界、符号链接、Origin/Host、密钥不回传、提示注入样例 | 假模型 | 每个 PR（CI） | 部分已有 |
| 前端测试 | 事件归并纯函数；App 冒烟（mock SDK 下渲染、导航、回放事件流）（Vitest + Testing Library + jsdom） | 无 | 每个 PR（CI） | 已有 |
| E2E | 验收主线（上传 → Skill → 产物 → 历史），Playwright | 假模型服务 | 合入前 / 每日 | S0 之后 |
| **Agent 评测** | 标准任务集上的成功率、步数、token、费用、耗时 | **真实模型** | 手动 / 定时，结果入库对比 | S2 |

## 原则

- **CI 中不调用真实付费模型。** 需要模型的测试使用脚本化假模型：按"第几步返回什么"编排工具调用，断言 Runtime 的行为（事件序列、工具参数、终止条件），而不是断言模型文本。
- **测行为，不测实现**：通过公开接口（HTTP API、Runtime 入口、工具注册表）测试；重构时测试应保持不变。
- **Bug 先复现**：修复前先写失败的回归测试。
- **安全边界必须有反例测试**：每条"禁止"规则都要有一个尝试越界并被拒绝的用例。
- **时间与随机性可控**：时钟、ID 生成可注入，避免依赖真实时间的脆弱测试。
- **测试隔离**：每个测试使用 `tmp_path` 下独立的数据目录与工作空间，不读写用户真实 `~/.codex`、`~/.claude`。

## Agent 评测（S2 详细设计）

评测回答"改了提示词/上下文策略/模型之后，Agent 是变好还是变坏"。初步设想：

- `evals/tasks/`：每个任务包含输入（消息 + 文件）、期望（产物存在、包含关键事实、未越权）与评分方式（规则断言优先，必要时 LLM 评分）。
- 指标：通过率、平均步数、输入/输出 token、费用、耗时、工具错误率。
- 每次运行记录模型、提示词版本与 Git 提交，便于对比。
- 参考：Inspect AI、OpenAI Evals、SWE-bench 的任务组织方式（S2 调研阶段核实）。

## 命令

```sh
make test        # pytest + 覆盖率报告（只统计，不设门槛），然后 Vitest
make check       # lint + 类型检查 + 测试 + 契约一致性，CI 运行同一命令
```

`tests/conftest.py` 的 autouse fixture 拦截真实 `httpx` 传输：任何测试一旦发出真实网络请求立即失败。

## 前端测试

- 配置：`frontend/vitest.config.ts`（jsdom），`src/test/setup.ts` 补 `scrollIntoView` 并在每个用例后 `cleanup()`。测试文件与源文件同目录，命名 `*.test.ts(x)`。
- 前端只经由 `src/api/client.ts` 访问后端，测试用 `vi.mock('./api/client', ...)` 整体替换，不发真实请求。事件流用 async generator 回放脚本化事件。
- 纯逻辑放进 `lib/`，用普通单测覆盖；展示组件可通过 props 与 `rerender` 验证运行状态转换，hooks 通过 App 级用例验证。按用户可见的文本、角色与 DOM 顺序断言（Testing Library 的 `getByRole` / `findByText`），不断言内部状态。
- 事件时间线覆盖正文与工具/Skill 交错、未知事件保留、失败/取消、完成后正文与展开状态不丢失。异步回放用例等待事件专有内容和流结束后的刷新，避免误把最初的保存回复当成时间线，也避免回退测试在事件到达前就通过。
- 时间线整合同时覆盖最新/历史轮次的模型记录入口：按需查询、旧 Run 未加载且无回复正文时仍可访问、记录入口位于产物之前；保留设置异步加载与记录组件的复制/刷新测试。
- 测试替身返回的对象要像真实服务端一样每次都是新对象：hooks 的依赖比较按引用进行，复用同一对象会掩盖重复订阅一类问题。

## 假模型：两层替身

| 替身 | 位置 | 替换的是什么 | 用于 |
| --- | --- | --- | --- |
| `ScriptedProvider` / `ScriptedProviderFactory` | `tests/support/scripted_provider.py` | 整个 Provider（不经过 HTTP） | Runtime / API 行为：事件序列、工具执行、终止条件、发给模型的消息 |
| `httpx.MockTransport` + 真实 `OpenAIChatProvider(transport=...)` | `tests/providers/test_openai_chat.py`、`test_api.py` 少量端到端用例 | 只替换网络 | 协议解析：SSE 分块、工具参数分片拼接、HTTP 错误分类、响应体不外泄 |

`ScriptedProvider` 的每一步可以是固定事件序列（`text_turn`、`tool_turn(call(...))`），也可以是"看到的消息 → 事件"的函数，从而根据工具结果做反应而不必解析提示词。它记录每次请求的 `requests` / `tools` / `models` 与 `closed`，测试据此断言 Runtime 发出了什么。`pytest` 的 `pythonpath` 包含 `tests`，用 `from support.scripted_provider import ...` 导入。

```python
factory = ScriptedProviderFactory([tool_turn(call("list_files")), text_turn("完成")])
app = create_app(tmp_path, provider_factory=factory)
...
assert factory.last.requests[1][-1].role == "tool"
```
