# 路线图

本项目按**学习主题**推进：每个主题对应 Agent 开发的一项核心能力，按 [process.md](process.md) 的六阶段完成，每个主题一份文档 `docs/features/<编号>-<名称>.md`。顺序已于 2026-11-03 与用户确认：S0 → S1 → S2 → S3 → …，后续主题顺序可在开始前再讨论。

## 已完成 · P0 首版

- [x] API 优先的 Web 聊天与历史会话、Web 模型配置（密钥不回传、不提交）
- [x] 文件上传、文件工具、Skill 加载与约定目录发现
- [x] SSE 持久事件、断线恢复、取消、生成产物
- [x] 模块化上下文构建（环境、规则、Skill 目录）与上下文清单
- [x] OpenAPI 与 TypeScript SDK

## 主题列表

| 编号 | 主题 | 学习问题 | 主要内容 | 调研候选（② 阶段核实） | 状态 |
| --- | --- | --- | --- | --- | --- |
| S0 | 工程地基 | 工业级项目的工程骨架长什么样？ | Python 3.12 升级、模块重构、ruff/mypy/ESLint、pre-commit、GitHub Actions CI、`make check`、契约检查、Provider 抽象 | LiteLLM、pydantic-ai 的 provider 层；Codex CLI 的仓库工程实践 | ① 需求定义 |
| S1 | Agent 循环 | Agent 的本质是什么？循环如何终止、出错如何恢复？ | 循环与终止条件、工具注册表、并行工具调用、错误恢复与重试、计划/todo 工具、步数与预算控制 | Anthropic《Building Effective Agents》、OpenAI Codex CLI、smolagents、OpenAI Agents SDK | 未开始 |
| S2 | 可观测与评测 | 如何知道 Agent 变好还是变坏？ | Trace/Span、token 与费用统计、评测任务集与评分、结果对比 | OpenTelemetry GenAI 语义约定、Langfuse、Inspect AI | 未开始 |
| S3 | 上下文工程 | 长任务如何不爆上下文、不丢重点？ | token 计数、工具结果截断、对话压缩（compaction）、提示缓存、上下文摘要 | Claude Code / Codex 的压缩机制、Manus 上下文工程文章、Cline | 未开始 |
| S4 | 工具与安全 | 如何让 Agent 能动手又不闯祸？ | Shell 工具 + 沙箱、权限与审批模式、确认状态机、MCP 客户端、提示注入防护 | Codex 沙箱（Seatbelt/Landlock）、Claude Code 权限模型、MCP 规范 | 未开始 |
| S5 | 记忆 | Agent 如何"认识"用户？ | 短期/长期记忆、显式偏好、来源与修正、检索 | Letta（MemGPT）、mem0、Claude Code 记忆文件 | 未开始 |
| S6 | 多 Agent | 何时拆分 Agent？上下文如何隔离？ | 子 Agent、委派、Main 与 Executor 共用 Runtime | Claude Code subagent、OpenAI Agents SDK handoff、LangGraph | 未开始 |
| S7 | 后台与调度 | 如何让 Agent 持续为我工作？ | 持久 Worker、租约与重试、定时委托（时区/有效期）、Heartbeat、通知 outbox | Temporal 思想、现有 Agent 产品的定时任务 | 未开始 |
| S8 | 多端与产品化 | 如何走出浏览器？ | 桌面端（Tauri/Electron）、Keychain、系统通知、IM 渠道 | — | 未开始 |

## 原 P1～P3 条目的归属

| 原条目 | 归入 |
| --- | --- |
| 事件联合类型、契约兼容检查、结构化错误统一、游标分页 | S0 |
| 真实服务的持续兼容性验证 | S0（录制回放）/ S2（评测） |
| 请求用量与费用记录 | S2 |
| 文件和 Skill 版本摘要、上下文摘要 | S3 |
| 确认资源与状态机、MCP、PTC 受限编排、沙箱执行 | S4 |
| 显式偏好、项目背景、历史决定 | S5 |
| Main 与 Executor、前台委派后台 | S6 |
| 持久 Worker、Delegation、定时、通知、Heartbeat | S7 |
| 桌面客户端、Keychain、本地 Connector | S8 |
| 详情面板、键盘操作、可访问性 | 随各主题的 UI 工作逐步完成 |

## 验收主线

上传笔记 → 使用周报 Skill → 读取来源 → 写入产物 → 预览下载 → 重开页面查看记录。

远期：每周五按上海时区生成周报，后台运行，完成后通知；取消委托后不再触发（S7）。
