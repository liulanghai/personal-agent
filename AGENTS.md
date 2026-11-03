# 项目代理指引（Codex / Claude Code 共用）

本文件是 AI 协作规则的**唯一来源**。Codex 直接读取本文件；Claude Code 通过 `CLAUDE.md` 中的 `@AGENTS.md` 导入。修改规则只改这里，`CLAUDE.md` 仅放 Claude 专有补充。

## 项目定位

栖 · Personal Agent 是一个**以学习 Agent 开发为首要目的**的个人 Agent 项目，长期目标是工业级质量。因此：

- 每个功能都是一次学习：先定义需求，再调研优秀 Agent 的实现，再讨论方案，最后实现并总结。
- AI 的价值在于帮助用户理解和决策，而不是替用户快速写完代码。解释"为什么"比给出"怎么做"更重要。

## 一、先讨论，后编码（最高优先级）

- 用户提出需求、Bug 或问题时，先讨论目标、现象、原因（区分**已验证结论**与**推测**）、方案、影响范围与取舍。
- 可以做只读检查来定位问题，但**不得把提问、报错截图或需求描述视为修改授权**。
- 获得用户对方案的明确确认后，才修改代码、配置或依赖。未确认时停留在分析与讨论阶段，不擅自编码、安装依赖或部署。
- 用户明确要求执行的文档记录可以直接完成。
- 确认只对当次讨论的范围有效；范围扩大或方案变化需重新确认。

## 二、Feature 开发流程

所有功能按 [docs/process.md](docs/process.md) 的六阶段推进，每个主题一份文档 `docs/features/<编号>-<名称>.md`（模板：[docs/features/TEMPLATE.md](docs/features/TEMPLATE.md)）。

```
① 需求 →[G1]→ ② 调研 →[G2]→ ③ 方案 →[G3]→ ④ 实现 → ⑤ 验证 → ⑥ 学习总结
```

- **关卡 G1/G2/G3 必须由用户明确确认**，AI 不得自行跨越。在文档的「关卡记录」中写下确认日期与结论。
- 开始工作前先读对应 Feature 文档，确认当前处于哪个阶段，只做该阶段的事。
- 调研阶段：每条结论附源码路径或文档链接；无法核实的标注「推测」。不凭记忆描述其他项目的实现。
- 学习总结（⑥）由用户执笔，AI 只提供骨架与素材。
- 路线图与主题顺序见 [docs/roadmap.md](docs/roadmap.md)。

## 三、开发规范

详见 [docs/conventions.md](docs/conventions.md)，要点：

- Git：`main` 受保护（必需检查 `check`，仅允许 squash，合并后自动删除分支）。分支 `feat/<编号>-<名称>`、`fix/…`、`docs/…`、`refactor/…`。提交信息用 Conventional Commits。
- GitHub 操作使用 `gh`：
  - 可直接执行：查看 PR/CI 状态与日志、推送功能分支、创建或编辑 PR 描述。
  - **合并 PR 仅在用户明确说「合并」后执行**，且 CI 必须通过；CI 失败一律不合并。
  - 修改仓库设置、删除非本次合并产生的分支、强推共享分支，需先征得用户同意。
- 单个 PR 只做一件事，建议 ≤ 400 行（不含生成文件）。
- Python 3.12；ruff（lint + format，行宽 100）、mypy；新代码必须带类型注解。
- TypeScript strict；ESLint + Prettier；组件按职责拆分。
- 代码标识符与注释用英文；文档、提交说明正文可用中文。
- 不写超长行和"压缩式"代码：可读性优先，本项目代码也是学习材料。

## 四、测试与验证

详见 [docs/testing.md](docs/testing.md)。

- 行为变更必须附带测试；Bug 修复先写能复现的失败测试。
- 测试中不得调用真实付费模型；使用脚本化假模型或录制回放。真实模型只用于 Agent 评测（手动/定时）。
- 修改 API 后运行 `make gen`，并提交 `docs/openapi.json` 与 `sdk/src/schema.d.ts`。
- 环境：`make install`（uv + npm，Python 3.12）。不要用 pip 直接安装依赖；增删依赖用 `uv add` / `uv remove` 并提交 `uv.lock`。
- 提交前运行 `make check`（ruff、ESLint、Prettier、mypy、tsc、pytest、OpenAPI/SDK 生成物一致性），CI 执行同一命令；格式问题用 `make fmt` 修复。
- `make check` 失败时先修复再提交，不得跳过或删减检查；确需放宽规则须在方案中说明。

- 如实报告：测试失败要贴出输出；跳过的步骤要说明；未验证的不得写成已验证。

## 五、安全与数据

- 密钥、`data/`、`.env`、个人运行数据、数据库、日志与缓存不得提交。
- 测试与文档中不出现真实密钥；示例使用 `test-key` 一类占位符。
- 涉及工具权限、文件边界、Shell、网络访问的改动，在方案阶段单独列出安全影响。
- 产品运行时的规则（工作空间内的 AGENTS.md/CLAUDE.md）与本仓库的开发规则相互独立，详见 [docs/context.md](docs/context.md)。

## 六、文档维护

- 代码与文档同一 PR 更新：架构变化改 `docs/architecture.md`，上下文相关改 `docs/context.md`，路线图状态改 `docs/roadmap.md`。
- 本文件或 `CLAUDE.md` 的协作规则变化时，两者须保持一致：通用规则只写在本文件。
- 每完成一个 Feature 阶段，更新该 Feature 文档的状态与关卡记录。
