# Claude Code 指引

@AGENTS.md

## Claude Code 专有补充

以上通用规则来自 `AGENTS.md`（Codex 同样读取），修改通用规则请改 `AGENTS.md`，不要在此重复。

- 计划与讨论阶段优先使用 Plan 模式或只读工具；未经用户确认不调用 Edit/Write 修改代码。
- 调研阶段可使用 WebSearch/WebFetch 或子代理阅读外部项目源码；引用时给出链接或文件路径。
- 不要把本仓库的开发规则写入 Claude 记忆以代替本文件；需要长期生效的规则写进 `AGENTS.md`。
