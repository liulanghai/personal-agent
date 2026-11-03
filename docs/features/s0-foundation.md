# S0 · 工程地基

| 项目 | 内容 |
| --- | --- |
| 状态 | ① 需求定义（草案，待 G1 确认） |
| 关联 | 路线图 S0 |
| 开始日期 | 2026-11-03 |

## 关卡记录

| 关卡 | 日期 | 结论 | 备注 |
| --- | --- | --- | --- |
| G1 需求确认 | | | |
| G2 调研讨论 | | | |
| G3 方案确认 | | | |

已确认的前置决策（2026-11-03）：S0 先于所有新功能；Python 升级到 3.12；主题按 S0 → S1 → S2 → S3 顺序推进；每个主题一份文档。

---

## ① 需求定义（草案）

> 以下为 AI 根据现状整理的草案，供讨论；G1 前可随意修改。

### 背景与问题

现有代码功能完整，但不适合长期迭代与作为学习材料：

- 代码密度过高：最长单行约 2800 字符，`frontend/src/main.tsx` 191 行中有 25 行超过 150 字符。
- 无 lint/格式化/类型检查配置，无 CI，`main` 可直接推送。
- `runtime.py` 中 Agent 循环与 Chat Completions HTTP 细节耦合，无法接入其他协议（如 Anthropic Messages）或在测试中替换 provider。
- Python 3.9 已停止维护。
- 测试只有集成层，无契约一致性检查。

### 目标（草案）

- 升级 Python 3.12，依赖管理切换到 uv（待讨论）。
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

### 待讨论问题

1. 依赖管理是否切换到 uv（本机已安装）？还是保留 pip + requirements.lock？
2. 类型检查选 mypy 还是 pyright？
3. Provider 抽象是否在 S0 定义完整接口，还是只做最小抽离、在 S1 再完善？
4. 前端重构与测试是否放在 S0，还是拆为独立的小主题？
5. PR 拆分粒度：建议「工具链+CI」→「后端模块拆分」→「Provider 抽象」→「前端拆分」四个 PR，是否认同？

---

## ② 业界调研

（G1 后开始）

## ③ 技术方案

（G2 后开始）

## ④ 实现记录

## ⑤ 验证与评测

## ⑥ 学习总结（用户执笔）
