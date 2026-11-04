# Agent 架构、故障恢复与上下文压缩问答

日期：2026-11-04。

本文由 AI 按用户要求整理本次学习讨论，用户回答为要点转述。它不是用户独立执笔的学习总结，
也不表示 S1、S3、S4、S5 已进入相应阶段或通过关卡。候选设计均未经实现授权。

## 1. 消息怎样经过 Agent？

**问题**：用户消息如何变成回复？模型请求工具后如何继续？

**用户回答**：经过 HTTP 接口层、Runtime，由 Provider 与模型交互。模型返回工具调用后，
本地执行工具，再把之前的消息、调用请求和结果交给模型，循环到没有工具调用。

**补充**：模型提出请求，程序负责校验、授权和执行。没有工具调用是正常结束条件之一；
异常、取消、步数和预算也可能终止循环。这里描述的是概念链路，不能据此认定项目实现了全部停止条件。

## 2. 为什么保存工具调用消息？Provider 与 Runtime 怎样分工？

**用户回答**：模型需要知道调用过哪些工具及其结果。Provider 屏蔽厂商 API 差异，
Runtime 决定继续还是结束循环。

**补充**：工具结果还需要通过调用标识与请求对应，同一工具可能被调用多次。
具体模型 API 对消息配对的要求需要单独核实。把循环放进 Provider 会耦合模型适配与执行编排。

**问题**：同时读取 A、B，其中 B 失败怎么办？

**用户回答**：并行执行，把 A 的结果与 B 的错误都返回模型。

**边界**：独立读取适合并行；有依赖或共享可变状态的工具不能直接套用。
局部失败可以作为明确的工具结果交回模型，不必丢弃其他成功结果。

## 3. 工具成功、模型请求超时，从哪里重试？

**用户回答**：从请求模型处重试；重跑整轮会导致重复追加。保存工具调用结果用于恢复。
用户当时说明项目还未处理这些恢复问题，此处未另行审计实现。

**补充**：需要保存调用请求、标识、结果和执行阶段，恢复完整消息链。
“副作用已发生，但结果尚未持久化就崩溃”仍有不确定窗口，保存结果本身不提供恰好一次保证。

**用户方案**：写入前记录文件状态，崩溃后回滚再写。

**讨论结论**：这是恢复方向，但记录旧状态本身不保证原子性。还需判断操作是否完成，
处理并发修改，并让恢复可安全重复；直接恢复旧文件可能删除其他进程后续写入。

## 4. 怎样用 operation_id 防止重复插入？

**用户回答**：事先生成 operation_id 作为主键，重试复用；有则忽略，没有则插入。

**纠正**：“先查后插”存在并发竞争，最终需要数据库唯一约束。例如：

```sql
INSERT INTO notes (operation_id, content)
VALUES (:operation_id, :content)
ON CONFLICT (operation_id) DO NOTHING;
```

幂等性是重复请求不产生重复效果；唯一约束防止同一编号重复入库；事务让多次写入一起成功或回滚。
已存在时可返回先前结果。还应识别同一编号携带不同内容的冲突，不能一概视为成功重试。
这套数据库例子不能直接解决任意文件或外部服务副作用。

## 5. 对话历史和模型上下文是一回事吗？

**用户回答**：不是，由 Context 决定保留哪些内容。

**补充**：历史记录发生过什么，上下文是本次模型实际看到的材料，还可能包括规则、工具定义和检索内容。
裁剪要保持消息结构，避免工具请求与结果脱节。

**用户提出的压缩方案**：保存原文并返回 ID，由模型生成概览，同时提供按 ID 查询原文的工具。

**讨论结论**：摘要与按需读取可以减少常驻信息，但摘要有损，原文可检索也不意味着模型一定会主动读取。
近期精确交互可以保留原文。该接口是候选设计，不是已核实的各家共同实现。

## 6. 普通信息和约束怎样区别处理？

**用户修正后的方案**：压缩时区分信息和约束；约束持续出现在上下文中，普通信息可用摘要和详情工具。

**补充与限定**：应保留当前有效、适用于当前任务的约束，并处理来源、范围、替代和失效，
不能永久累积所有历史要求。文件或工具输出中的文字不能仅因语气像命令就被提升为授权。
路径权限等可形式化约束还需要工具执行层校验。

## 7. 原文读取工具的 ID 访问限制放在哪里？

**讨论答案**：Runtime 提供可信的用户、会话身份；工具／存储访问层在每次读取时强制检查归属。
模型提供的 record_id 只定位记录，不代表访问授权。用于授权的 user_id、session_id 不应由模型任意指定。
Context 可以解释访问范围，但不能替代访问控制。跨会话检索须按产品的明确授权策略开放。

## 8. 优秀 harness 的公开机制

以下是本次查阅官方文档后的记录，不是完整源码审计；产品文档会变化。

| 对象 | 已查阅的机制 | 学习启发 |
| --- | --- | --- |
| Codex | AGENTS.md 具有独立发现机制；官方指南介绍原生 compaction | 规则状态与历史压缩分别管理 |
| Claude Code | 官方文档说明压缩后重新注入根目录 CLAUDE.md，嵌套规则按需加载；聊天指令可能丢失 | 从规则源恢复，不能只依赖摘要 |
| OpenCode V2 | 官方文档描述摘要与近期原文并存，旧消息仍存储 | 区分持久历史与模型可见窗口，注意版本差异 |

参考：

- [Codex 规则发现](https://learn.chatgpt.com/docs/agent-configuration/agents-md)
- [Codex Prompting Guide](https://developers.openai.com/cookbook/examples/gpt-5/codex_prompting_guide)
- [OpenAI Compaction](https://developers.openai.com/api/docs/guides/compaction)
- [Claude Code memory](https://code.claude.com/docs/en/memory)
- [Claude Code permissions](https://code.claude.com/docs/en/permissions)
- [OpenCode V2 compaction](https://dev.opencode.ai/v2/docs/compaction/)
- [OpenCode V2 instructions](https://dev.opencode.ai/v2/docs/instructions/)
- [Anthropic context engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)

## 9. Codex 源码：规则怎样变成消息、跨越压缩？

本次本地源码版本：`48524f337a`，仓库 `openai/codex`。
源码位于本地 `references/codex/`，通过 `.git/info/exclude` 排除，不提交到本项目。
以下使用远程版本链接，便于没有本地副本时查看。

**规则消息**：`UserInstructions` 返回 user 角色，附带 `agents_md.instructions` 类型，
正文用 `# AGENTS.md instructions` 和 `<INSTRUCTIONS>` 包装。
见 [context/user_instructions.rs](https://github.com/openai/codex/blob/48524f337a/codex-rs/core/src/context/user_instructions.rs)。

**AgentsMdState**：保存已加载的 `Option<UserInstructions>`；正文及目录另有快照结构。
它比较当前状态与先前快照：不变则不重复发送，变化则发送替代说明，移除则发送失效说明。
见 [context/world_state/agents_md.rs](https://github.com/openai/codex/blob/48524f337a/codex-rs/core/src/context/world_state/agents_md.rs)。

**用户理解与纠正**：用户将其理解为规则变化后的更新覆盖机制。
准确地说，它更新模型上下文中的规则表达，不修改磁盘文件、不自动提取聊天规则，
也不负责决定何时重新读取文件。

**压缩重建**：`build_compaction_replacement_history` 调用
`build_initial_context_with_world_state`，将重建上下文加入压缩后的历史；远程 V2 安装路径也调用相关重建机制。
因此，AGENTS.md 可由 harness 状态重新注入，不必完全依赖摘要。这不等于每次重新读磁盘或保证模型遵守。
见 [compact.rs](https://github.com/openai/codex/blob/48524f337a/codex-rs/core/src/compact.rs)
和 [compact_remote_v2_installation.rs](https://github.com/openai/codex/blob/48524f337a/codex-rs/core/src/compact_remote_v2_installation.rs)。

**聊天新增规则**：“以后先验证再提交”首先是普通用户消息。本次检查的本地压缩路径倒序保留用户消息，
上限约 20,000 tokens；摘要提示要求保留约束与用户偏好。两者都不能保证任意早期要求永远保留。
未发现这些已检查路径会自动把任意聊天要求转成独立持久规则，不能据此断言整个产品绝无其他机制。
也不能把本地压缩预算推广到所有远程实现。
见上述 `compact.rs` 和 [压缩提示词](https://github.com/openai/codex/blob/48524f337a/codex-rs/prompts/templates/compact/prompt.md)。

## 10. “这次只改文档”为什么容易在压缩后误用？

**场景**：默认提交前跑完整测试；用户后来授权“这次只改文档，检查格式就行”。

**用户回答**：只对本次任务例外，其他会话仍读 AGENTS.md；没写入就不会生效。

**纠正**：未写入文件，不代表当前任务不生效；它只是不因此成为跨会话持久规则。
例外结束后，默认要求仍有效。

**反例**：摘要只保留“提交前检查格式即可”，丢失“这次”“只改文档”，
就把有限授权扩大成了通用授权。用户指出这样可能在改代码后仅检查格式便提交，并表示暂时想不到解决办法。

**候选设计**：将重要例外与条件作为整体独立记录：

```text
默认规则：提交前跑完整测试
例外：仅检查格式
范围：当前任务
条件：实际变更仅包含文档
来源：用户原始消息 ID
失效：任务结束，或实际变更包含代码
```

重建上下文时注入有效规则与例外；提交入口根据实际 diff、当前代码版本对应的验证结果检查条件。
自然语言提取和任务边界判断仍可能出错，重要歧义需澄清。这是讨论中的方案，未实现。
本文示例不改变本仓库既有的 `make check` 要求，也不授权跳过检查。

## 11. 复习与待探索

- 内容保留、模型遵守、程序强制限制是三种不同保证。
- 摘要帮助延续理解；独立规则状态提高内容保留可靠性；执行层落实可判断的权限与前置条件。
- 仍待研究：聊天规则如何识别与确认、任务范围如何界定、条件怎样撤销、摘要怎样保留来源且避免授权升级。
- 可以用反例检验方案：并发重复请求、崩溃窗口、重复压缩、规则冲突、跨会话 ID、过期验证结果。
- 后续讨论继续采用“一次一个问题 → 用户回答 → 针对反馈 → 具体边界追问”的方式；不把候选方案当成已实现能力。
