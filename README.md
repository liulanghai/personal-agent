# 栖 · Personal Agent

本地运行、API 优先的个人 Agent。通过 Web 交互，在网页配置模型，使用文件工具与 Skill 完成任务。代码、技能、API 契约、测试和文档统一由 Git 管理。

## 开发环境

- Python 3.9+（当前开发机为 3.9；新环境建议使用较新的受支持版本）
- Node.js 22.12+

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.lock
npm ci
npm run build
```

启动：双击 `scripts/start.command`，或在项目目录执行：

```sh
.venv/bin/python -m uvicorn agent.app:create_app --factory --app-dir backend --host 127.0.0.1 --port 8000
```

打开 http://127.0.0.1:8000 。首次使用为演示模式，无需密钥。在「设置与模型」配置 Base URL、模型名称、API 密钥后，切换到真实模型模式。兼容端点须支持 Chat Completions 流式输出和 function tools。保存设置不等于服务连通测试，首次发送消息会实际验证服务。

开发热更新：后端按上面的命令启动，另一个终端运行 `npm run dev`，访问 http://127.0.0.1:5173 。

## 首次验收

1. 打开网页，通过「整理本周进展」上传 `examples/notes.md`。
2. 选择「周报生成」技能并发送消息。
3. 展开真实工具调用，查看 `read_skill`、`list_files`、`read_file`、`write_file`。
4. 预览、下载产物，刷新页面后重新选择会话验证历史记录。
5. 在设置页配置模型，再发起真实任务。

演示模式只汇编原文片段，不进行 AI 总结，界面与产物均明确标注。

## 当前功能与边界

- Web 聊天、流式回复、历史消息、执行详情、取消任务。
- 文件上传（UTF-8，最大 60KB）、目录约束、只创建产物不覆盖源文件。
- 本地 Skill 发现与按需加载，内置文档总结和周报生成。
- SQLite 会话/任务/事件持久化；SSE 可重放，前端断线重连。
- 页面关闭不取消任务；后端进程停止会中断任务，重启时标为失败，不自动重放动作。
- 本地演示模式、可配置兼容模型服务；尚未用用户真实密钥验证特定服务。
- 本版不含 MCP、Shell、浏览器控制、长期记忆、定时任务或桌面壳。

## 密钥与数据

模型密钥只在输入时发送给本地后端。后端存于 `data/settings.json`，文件权限 `0600`，父目录权限 `0700`；它是本地明文文件，尚未接入系统 Keychain。GET 设置只返回 `has_api_key`，不返回密钥。更换服务地址须重新输入密钥，避免旧密钥误发给新服务。

`data/`、`.env`、依赖和构建产物均在 `.gitignore` 中。运行数据不进入 Git；示例资料可以提交。真实模型模式会将会话内容、选定文件和相关工具结果发送到配置的模型服务。

服务默认只监听 loopback，校验 API Origin 与本机 Host。若扩展到远程访问，必须设置 `AGENT_API_TOKEN` 并补充 HTTPS、用户隔离、部署安全策略。当前为单用户模式。Web 预留 API token 的 sessionStorage 读取，尚无登录 UI；普通本地使用不需要 token。

## API、SDK 与验证

- API 文档：http://127.0.0.1:8000/docs
- 契约：`docs/openapi.json`
- TypeScript SDK：`sdk/src/index.ts`
- 架构：`docs/architecture.md`
- 路线图：`docs/roadmap.md`

```sh
npm run sdk:generate
npm run build
.venv/bin/python -m pytest -q
```

SDK 以配置 Base URL 的方式供 Web 和未来自建桌面端复用；接入 OpenAI 官方 Codex 应用需另核实官方扩展能力，本项目不保证该集成。

## Git 工作方式

当前仓库为本地 `main` 分支，未创建远程仓库。代码、文档、Skill、SDK、OpenAPI、依赖锁文件和测试全部提交。修改 API 后重新生成契约与类型；提交前运行上述检查。不提交用户资料、密钥、数据库、日志和构建缓存。
