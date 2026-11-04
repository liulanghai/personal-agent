# 架构与 API 约定

## 职责

React Web → TypeScript SDK → FastAPI `/api/v1` → Runtime → 工具/Skill → SQLite 与本地文件。

Web 不直接访问模型、工作目录或数据库。桌面端可复用 SDK，连接本地或远端后端。Runtime 不依赖前端；SSE 消费者离开后，任务仍在后端 asyncio task 中运行。首版为一个服务进程，启动 uvicorn 时不得配置多个 worker。多进程、进程级重试和排队调度留待持久 Worker 阶段。

Conversation 是持续会话；Run 是一次执行。首版同一会话只允许一个活跃 Run，其他会话可并发。Tools 的参数由 JSON Schema 校验。Skill 是流程资料，无权扩展执行权限。

## 后端模块

```
backend/agent/
  app.py              create_app：只做组装（配置、存储、工具、Runtime、中间件、路由、静态文件）
  config.py           SettingsStore：settings.json / 环境变量读取、校验、0600 原子写入
  security.py         Origin / Bearer / 回环 Host 校验中间件
  store.py            SQLite；全部 SQL 只在此处，对外为具名方法 + TypedDict 行类型
  api/
    schemas.py        请求/响应模型（OpenAPI 与 SDK 的来源）
    errors.py         统一错误格式
    deps.py           Services 容器与 require_* 查询（不存在时 404）
    routes/           system · settings · conversations · runs · skills · files（APIRouter）
  runtime/
    runtime.py        Run 生命周期：launch / execute / cancel / 启动时中断恢复 / 关闭
    loop.py           Agent 循环：消费 Provider 事件、执行工具调用、步数上限
  providers/
    base.py           中立类型（Message / ToolCall / StreamEvent）、ProviderError、Provider 协议
    openai_chat.py    OpenAIChatProvider：消息映射、SSE 解析、工具参数分片拼接、错误分类
    recording.py      可选本机交互记录：任务作用域、凭证脱敏、增量保存与终态
  tools/
    registry.py       工具定义（JSON Schema）、参数校验、分发；Tools 门面
    paths.py          工作空间边界：唯一的路径校验实现
    files.py          list / read / search / write
    skills.py         list_skills / read_skill / read_skill_resource
  context/
    builder.py        ContextBuilder
    discovery.py      规则与 Skill 发现
```

依赖方向：`api → runtime → providers/context/tools → store`；路由与 Runtime 不拼写 SQL，路径校验只经由 `tools/paths.py`。所有模块均通过 mypy strict。

Runtime 只认识 `providers.base` 中的中立类型，不接触 HTTP、SSE 或厂商 JSON。Provider 由 `create_app(provider_factory=...)` 注入（默认 `openai_chat.from_settings`），每个 Run 开始时按当次设置创建一个，Run 结束时 `aclose()`；执行中不切换。Provider 错误统一为 `ProviderError(kind, retryable)`，其消息面向用户，不包含响应体。

## 前端模块

```
frontend/src/
  main.tsx            挂载入口
  App.tsx             页面切换与组装；草稿、附件、技能选择、发送、上传、预览
  api/client.ts       AgentClient 单例：前端访问后端的唯一入口
  hooks/
    useConversation   当前会话及其 messages / runs / artifacts（唯一所有者）；isCurrent 丢弃迟到响应
    useRunEvents      最新 Run 的 SSE 订阅：Last-Event-ID 续传、连续失败上限；只持有 events / live
  lib/                纯函数：事件归并（events）、按 Run 分轮次（turns）、文案与状态（labels）、下载（download）
  components/         展示组件，数据与回调由 props 传入；SettingsPanel、TaskPanel、ModelCalls 各自加载所需数据
```

数据流：`useRunEvents` 不修改消息或 Run，而是通过 `onRunStarted` / `onSettled` / `onDisconnected` 回调交给 `useConversation`。事件订阅只在 Run 或会话变化时重启；Run 对象的字段更新（如状态变为 running）不会触发重订阅。

对话按轮次（一个 Run 一轮，以消息与产物的 `run_id` 分组）展示：提问 → 执行过程（第一行为上下文清单，完成后折叠）→ 回复 → 产物。每轮执行过程均提供模型调用入口；最新轮次还展示订阅到的上下文与工具事件，历史轮次不回放这些事件，也不把未加载的工具数量显示成零。`ModelCalls` 展开后按 Run 查询记录，活跃 Run 每 2 秒刷新；先查询 Run 状态再读取记录，确保终态后读取包含最后一次调用。重新打开页面可读取持久记录，详情与 JSON 默认折叠，可复制。

## HTTP

路径统一为 `/api/v1`。创建会话返回 201；发送消息返回 202 和 Run。`Idempotency-Key` 保证同一请求重试返回同一 Run；相同 key 不同输入返回 409。发送超时但不确定是否成功时，客户端必须使用原 key 重试；首版 Web 出错后不会自动重试发送。

HTTP 业务错误格式为 `{ "error": { "code": "...", "message": "..." } }`；FastAPI 请求结构校验目前保留标准 422 `detail` 数组，SDK 兼容该格式。

会话、消息、Skill 当前不分页；执行和产物列表最多 100 条，面向本地单用户首版。规模扩大前需要加入稳定游标分页。

## 事件

GET `/runs/{id}/events` 使用 SSE。每个事件包含 `id`、全局递增 `sequence`、`run_id`、`type`、`data`、`created_at`。sequence 可有间隔，客户端不能假设连续。事件写入数据库后才推送。

- `run.started`: 空对象
- `context.built`: 模块清单、规则来源摘要、环境快照与预算（详见 context.md）
- `message.delta`: delta
- `tool_call.started`: tool_call_id, tool_name, arguments
- `tool_call.completed`: tool_call_id, tool_name, status, result
- `artifact.created`: id, name, path, size
- `run.completed` / `run.cancelled`: 空对象
- `run.failed`: error

使用 `Last-Event-ID` 或 `after` 顺序号恢复。终态的事件全部输出后关闭流。SDK 使用 fetch 流，允许 Authorization 请求头；客户端按事件 ID 去重/续读。事件是执行记录而非模型内部思维。

## 持久化与恢复

数据库保存 conversation/message/run/event/file/model_calls。执行错误为失败终态，工具错误作为结构化结果交回模型。中止状态持久化。服务启动时将未结束 Run 标记失败，防止盲目重复副作用。首版取消或失败的部分模型文本保存在事件里，不作为完整 assistant 消息进入后续模型历史。

新增文件只允许写入 reports/；禁止越出 workspace，解析符号链接后再次检查目录归属。此限制保护宿主目录，但还不是对恶意本机用户的隔离沙箱。禁止直接执行模型生成的任意代码。

## 模型配置

PUT `/settings` 接收 base_url、model、api_key。api_key 为 null 时保留，空字符串清除；切换 base_url 且存在旧密钥时必须显式输入新密钥。GET 仅返回 has_api_key。配置持久化到忽略的 data 目录。任务开始时读取配置；进行中的任务使用已读入的配置，不中途切换 provider。

## 可选模型交互记录

`record_model_calls` 默认关闭，经 GET/PUT `/settings` 读写；旧客户端省略该字段时保留原值。设置与模型配置一起在 Run 开始时读取，关闭影响后续 Run，已有记录继续保留。网页提示记录会包含对话、工具结果和文件正文。

`AgentLoop` 通过任务局部 `ContextVar` 绑定 Store、Run 与 Conversation。`OpenAIChatProvider` 在每次 HTTP 请求边界创建一条记录，因此一次包含工具往返的 Run 可以对应多次调用；注入的假 Provider 不制造 HTTP 记录，不同任务的作用域相互隔离。

专用 `model_calls` 表按 Run 内序号保存接口、请求 JSON、接收到的原始 SSE 文本、拼接后的回复与工具调用、usage（服务端有返回时）、HTTP 状态、耗时及错误。原始文本保留换行，经过 HTTPX 字符解码与凭证脱敏，并非网络字节抓包；解析在 `[DONE]` 结束，不保证保留结束标记后尚未接收的字节。不额外发送 `stream_options`。JSON 错误响应也保留解析后的 body。

接收片段时同步持久化，失败和取消保留已接收内容；启动恢复把遗留的 running 调用标记为 interrupted。请求和响应 headers 均不保存，URL 去除用户信息、全部 query 与 fragment；配置密钥及 URL 中凭证的常见 URL/JSON 编码回显会被替换为 `[REDACTED]`。跨片段的凭证前缀暂缓写入，结束时仍不明文写回。解析异常转换为不含原文的安全错误。记录不进入普通 Run 事件或应用日志。

GET `/runs/{id}/model-calls` 按序返回记录，未知 Run 返回 404，沿用现有 API 安全中间件。详情见 [模型交互记录功能文档](features/aux-model-call-recording.md)。当前无自动清理、分页或全文大小上限；逐片段同步 SQLite 写入适合本机学习，长响应的内存、磁盘与写入开销需要后续优化。

## 技术参考

- 需求来源：[从零打造 Personal Agent（一）](https://my.feishu.cn/wiki/MYdcwUK1Ei53k2kWt1EcowNAnDc)。按职责分层，分阶段实现；不依赖文中产品能力的推测。
- [FastAPI StreamingResponse](https://fastapi.tiangolo.com/advanced/custom-response/#streamingresponse)
- [Vite 开发指南](https://vite.dev/guide/)
- [React TypeScript](https://react.dev/learn/typescript)
- [Chat Completions API](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create)

## 移除演示分支

所有 Run 直接调用模型；不再提供 mode 配置或演示回退。旧 settings.json 中的 mode 字段被忽略，地址、模型名和密钥继续沿用；无需改写旧配置。请求/响应契约及 SDK 已同步更新。清除密钥仍可保存，但后续执行会明确报告未配置。
