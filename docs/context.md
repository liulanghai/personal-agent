# 上下文构建、规则与技能发现

## 模块边界

- `backend/agent/context.py`：ContextBuilder，在每个 Run 的首次模型调用前构建上下文。
- `backend/agent/discovery.py`：发现约定位置的规则和 Skill；不执行脚本。
- Runtime：调用构建器，持久化 `context.built` 事件，再执行模型/工具循环。
- Tools：文件边界与参数校验仍由工具层执行，规则文件不能增加权限。

ContextBuilder 的 provider 列表可注入扩展。每个 provider 返回 name、data、可选 warnings；以后可以加入任务进度、相关记忆等模块，无需改写模型循环。

## 环境模块

每个新 Run 读取当前 UTC 时钟，按用户设置的 IANA 时区计算日期、星期、带偏移量的时间。默认 Asia/Shanghai，可在 Web 设置修改。不依赖服务进程所在时区。还包括工作空间绝对路径、宿主 OS、Shell、会话/执行 ID、文件读写和 Shell 权限摘要。

当前采用 Run 开始时快照；长任务内未定时刷新时间，后续可扩展时间工具或刷新策略。UI 上的消息显示时间仍使用浏览器时区，与模型使用的可配置时区相互独立。

## 工作空间

默认 `data/workspace`。可通过 `.env` 或进程环境变量 `AGENT_WORKSPACE=/absolute/project/path` 指定，重启服务生效。规则与项目级技能绑定到该目录；不会向上扫描到软件源码目录，因此源码中的开发协作规则不会自动污染产品运行规则。

更换工作空间应使用独立 AGENT_DATA_DIR，以免旧数据库的文件记录指向不同空间。本版不支持执行中切换目录或多个工作空间。Web 显示当前路径，暂不提供目录选择器。

## 规则发现

Web 中可选择 auto / codex / claude。按用户级→项目级加载。

| 范围 | Codex 候选顺序 | Claude 候选顺序 |
| --- | --- | --- |
| 用户 | `$CODEX_HOME/AGENTS.override.md`、`AGENTS.md`；默认 CODEX_HOME 为 `~/.codex` | `~/.claude/CLAUDE.md` |
| 项目 | `<workspace>/AGENTS.override.md`、`AGENTS.md` | `<workspace>/CLAUDE.md`、`.claude/CLAUDE.md` |

auto 在每层优先 Codex 候选，缺失或空白时回退 Claude。同层只加载第一个非空文件，其他文件记录为 warnings，界面显示。规则以 user 角色消息加入，上层应用约束仍为 system 消息。规则来源路径、scope、内容摘要记入清单。

当前覆盖工作空间根目录的规则发现，不实现子目录切换、`@import` 展开、`.claude/rules` 的路径过滤或全部产品专有语义。规则正文中的引用保留原文，不自动展开；需要生效的规则应直接写在选中的标准文件中。单文件上限 60KB；不可读或超限规则会明确报错，不静默忽略。

## Skill 发现

扫描以下位置的 `<skill>/SKILL.md`：

1. `<workspace>/.agents/skills`
2. `<workspace>/.claude/skills`
3. `~/.agents/skills`
4. `~/.claude/skills`
5. `$CODEX_HOME/skills`（兼容旧目录，以及 `.system/` 下的打包技能）
6. 本项目 `skills/`（内置默认技能）

支持符号链接，同一个实际 SKILL.md 只发现一次。使用 YAML 解析 name / description，支持多行描述。目录扫描不执行脚本；名称与描述加入目录，正文只在 read_skill 时加载。格式错误文件列为 warning，不拖垮整个目录。

重名技能保留全部来源，ID 增加路径摘要，不静默覆盖。列表 ID 来自 frontmatter name，前端显示名称和来源，调用必须使用 API 返回的 ID。重复名称的出现或消失可能使 ID 改变，因此每次新执行前重新发现，而不长期缓存技能 ID。

`read_skill_resource(skill_id, path)` 可读取选中技能内的文本模板和参考资料，解析符号链接后禁止越出技能目录；不授予宿主任意文件读取或脚本执行权限。脚本、二进制资源、hooks、allowed-tools、禁用模型调用等扩展语义未实现；未支持的 frontmatter 字段会在列表标记，不模拟生效。兼容的是标准文件格式与发现位置，不是完整复刻 Codex / Claude Code。

技能页支持刷新；API 每次请求重新扫描，新增目录无需修改代码。

## API 与可观测性

- GET `/api/v1/discovery`：当前工作空间、选中规则来源、技能列表、warnings。
- GET `/api/v1/runs/{id}/context`：该任务持久化的构建清单（历史任务可能没有）。
- SSE `context.built`：模块名、长度、SHA256、规则来源、环境快照和 warnings。
- Web 对话中的「查看本次上下文与环境信息」显示清单。

完整规则正文和历史材料不重复存入清单；不加入模型密钥。当前预算是 160000 字符，并非 token 估算；超限明确失败，不静默截断。规则和目录按任务开始时生成快照，工具调用结果随后追加。

## 参考

- [Codex AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md)
- [Codex Skills](https://learn.chatgpt.com/docs/build-skills)
- [Claude Code 规则](https://code.claude.com/docs/en/memory)
- [Claude Code Skills](https://code.claude.com/docs/en/skills)
