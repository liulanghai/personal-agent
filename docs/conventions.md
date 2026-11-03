# 开发规范

> 状态说明：标注「S0 落地」的条目由 S0 工程地基主题实现工具链后强制执行；在此之前作为约定遵守。

## Git 与 PR

- `main` 为受保护分支：禁止直接推送，只能通过 PR 合入，合并方式为 squash（S0 落地）。
- 分支命名：`feat/<编号>-<短名>`、`fix/<短名>`、`docs/<短名>`、`refactor/<短名>`、`chore/<短名>`。
- 提交信息遵循 [Conventional Commits](https://www.conventionalcommits.org/zh-hans/)：`feat:`、`fix:`、`docs:`、`refactor:`、`test:`、`chore:`、`ci:`。标题 ≤ 72 字符，正文说明"为什么"。
- 一个 PR 只做一件事，建议 ≤ 400 行（不含 `docs/openapi.json`、`sdk/src/schema.d.ts`、锁文件等生成文件）。
- PR 描述包含：关联主题文档/Issue、变更摘要、测试方式、风险与回滚、截图（涉及 UI 时）。
- 生成文件（OpenAPI、SDK 类型、锁文件）与源变更放在同一 PR。

## 目录结构

当前结构（S0 会重构）：

```
backend/agent/   FastAPI 应用、Runtime、工具、上下文、存储
frontend/        React + Vite Web
sdk/             TypeScript SDK（由 OpenAPI 生成类型）
skills/          内置 Skill
tests/           pytest 测试
docs/            架构、流程、规范、主题文档、学习总结
scripts/         启动与生成脚本
```

S0 目标结构（以 S0 方案阶段确认的版本为准）：

```
backend/agent/
  api/         HTTP 路由、请求/响应模型、错误处理
  runtime/     Agent 循环、Run 生命周期、事件
  providers/   模型协议适配（OpenAI Chat Completions、Anthropic Messages…）
  tools/       工具注册表与各工具实现
  context/     上下文构建、规则与 Skill 发现
  store/       持久化
  config.py    配置
```

## Python

- 版本：Python 3.12（`requires-python = ">=3.12"`，S0 落地）。依赖管理使用 uv 与锁文件。
- 格式化与 lint：ruff，行宽 100；启用 `E,F,I,B,UP,SIM,ASYNC` 等规则（S0 落地）。
- 类型：mypy（或 pyright），新代码必须带类型注解；公共函数参数与返回值不可省略。
- 数据结构：跨模块传递的数据使用 Pydantic 模型或 dataclass，避免裸 `dict` 在多层间传递。
- 异步：IO 一律 async；禁止在事件循环中执行阻塞调用（文件大量读写使用线程池）。
- 错误：业务错误使用自定义异常类型并映射为统一错误格式；不吞异常；不向日志或事件写入密钥与 provider 原始响应体。
- 日志：使用标准 `logging`，结构化字段；不使用 `print`。

## TypeScript / 前端

- `strict: true`；ESLint + Prettier（S0 落地）。
- 组件按职责拆分到 `components/`，数据获取与状态放在 `hooks/`；单文件建议 ≤ 300 行。
- 前端只通过 SDK 访问后端，不手写 fetch。
- 禁止 `any`，确需时使用 `unknown` 并收窄。

## 通用编码原则

- **可读性优先**：本项目代码也是学习材料。禁止把多条语句压缩到一行；单行 ≤ 100 字符（Python）/ Prettier 默认（TS）。
- 标识符与代码注释使用英文；注释解释"为什么"，不复述代码。
- 先写最简单可行的实现，抽象在出现第二个使用者时再提取。
- 安全边界（文件路径、权限、外部调用）集中在一处实现并有测试，不在调用方各自判断。

## 依赖

- 新增依赖需在方案阶段说明理由与替代方案；优先标准库与已有依赖。
- 锁文件随依赖变更一起提交；定期运行 `npm audit` 与 `pip-audit`（S0 落地）。

## API 演进

- 路径前缀 `/api/v1`；破坏性变更需新版本或兼容期，在 PR 中显式标注。
- 修改 API 后运行 `npm run sdk:generate`，CI 检查生成文件与源码一致（S0 落地）。
- 事件类型新增字段向后兼容；删除或改名视为破坏性变更。

## 文档

- 架构变化 → `docs/architecture.md`；上下文相关 → `docs/context.md`；路线图状态 → `docs/roadmap.md`；主题进展 → `docs/features/`。
- 文档描述"当前事实"，过时内容在同一 PR 中修正，不保留"计划中"与"已实现"混杂的描述。
