# 文档路由表（DOCS_ROUTING）

> 最后校对：2026-08-08
> 用途：从项目任意入口都能快速定位「该看哪个文档」
> 适用：开发者、维护者、新接入贡献者、Agent（自身）

---

## 1. 项目门面（根目录）

| 文件 | 作用 | 何时打开 |
|---|---|---|
| [README.md](README.md) | 项目门面（英文）：定位、技术栈、快速开始、安全 | 新人入门；查询对外文档 |
| [README_zh.md](README_zh.md) | 项目门面（中文）：上述的中文版 | 同上 |
| [AGENTS.md](AGENTS.md) | Trae / 编码 Agent 工作规则（会话流程、子 Agent 调度、日志、文档规范） | 每个 Agent 会话开始 |
| [CONTRIBUTING.md](CONTRIBUTING.md) | 贡献指南（开发环境、Docker / 本地两种路径） | 准备 PR |
| [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) | 社区行为准则 | 任何社区互动 |
| [SECURITY.md](SECURITY.md) | 安全策略（如何上报漏洞） | 发现安全问题时 |
| [RELEASING.md](RELEASING.md) | 发布流程（版本源、tag 驱动、CI 版本门禁） | 打 tag / 发布 |
| [CHANGELOG.md](CHANGELOG.md) | 更新日志（英文，Keep a Changelog） | 查看变更 |
| [CHANGELOG_zh.md](CHANGELOG_zh.md) | 更新日志（中文版） | 同上 |
| [LICENSE](LICENSE) | MIT 许可证 | 法律查询 |
| [DOCS_ROUTING.md](DOCS_ROUTING.md) | **本文档**：所有文档的目录索引 | 不知道看哪里时 |

---

## 2. `docs/` — 项目级专题文档（本次二次开发的核心交付）

### 2.1 功能模块专题（按业务域）

每个目录对应**一个业务子系统的完整设计文档包**（需求 / 架构 / 数据库 / 接口 / 审计）。文件命名统一为 `requirements.md / architecture.md / database.md / api.md`，审计需求视模块而定。

| 子目录 | 业务子系统 | 何时打开 |
|---|---|---|
| [docs/git-integration/](docs/git-integration/) | **Git 源代码管理**：文件夹↔仓库绑定、SSE 拉取/推送、GitHub/Gitee 令牌按账号隔离、令牌获取帮助卡片 | 调整 Git 集成功能、查审计 |
| [docs/workspace/](docs/workspace/) | **个人工作空间**：三级层级（工作空间 → 文件夹 → 文件），会话绑定文件夹加载文档入上下文 | 调整工作空间 / 文件管理 |
| [docs/mutil-agents/](docs/mutil-agents/) | **多 Agent 工作流引擎**：DAG 节点/边、SSE 执行流、分步执行详情 | 调整工作流引擎 |
| [docs/user-mcp/](docs/user-mcp/) | **用户级 MCP 服务器注册**：stdio/sse/http、按账号隔离、工具运行时解析 | 调整 MCP 用户注册 / 工具过滤 |
| [docs/user-settings/](docs/user-settings/) | **用户级设置（千人千面）**：渠道、集成、工具偏好、Git 令牌等 | 调整设置面板、用户隔离 |

每个子目录内统一含：
- `requirements.md` — 需求（含业务流程图 Mermaid，L5）
- `architecture.md` — 系统架构（含架构图 Mermaid，L4）
- `database.md` — 数据库设计（含 ER 图 Mermaid，L4）
- `api.md` — 接口设计（含时序图 Mermaid，L4）
- `audit-requirements.md`（部分模块）— 审计要求（L5）

### 2.2 其他专项

| 文件 | 作用 |
|---|---|
| [docs/database/README.md](docs/database/README.md) | 数据库总览：当前唯一 PostgreSQL 后端（DSN + schema），"很多库"来源说明，种子数据清单 |
| [docs/database/active-tianshu-schema.sql](docs/database/active-tianshu-schema.sql) | `tianshu` schema 下 31 张表的 `CREATE TABLE`（含 PK/UNIQUE/FK） |
| [docs/database/active-tianshu-seed.sql](docs/database/active-tianshu-seed.sql) | 种子表 INSERT 语句（users / agents / workflows / workspaces / folders / files 等） |
| [docs/agents/maintainer-orchestrator-design.md](docs/agents/maintainer-orchestrator-design.md) | Maintainer Orchestrator skill 设计笔记：边界、安全原则、为什么这样设计（用于社区理解与改造） |
| [docs/OPENVIKING.md](docs/OPENVIKING.md) | OpenViking 远程记忆后端（可选）：与 DeerMem 并存的 pluggable `MemoryManager` |
| [docs/SKILL_NAME_CONFLICT_FIX.md](docs/SKILL_NAME_CONFLICT_FIX.md) | 技能名称冲突修复记录：public skill 与 custom skill 同名冲突的代码改动文档 |
| [docs/upload.md](docs/upload.md) | 上传功能增强建议（按 AI Agent 行业趋势与项目架构分维度） |
| [docs/CODE_CHANGE_SUMMARY_BY_FILE.md](docs/CODE_CHANGE_SUMMARY_BY_FILE.md) | 代码改动总结（基于 `git diff HEAD`，按文件细化到行） |

---

## 3. `backend/docs/` — 后端运行时文档（已沉淀）

> 后端 Python 包的详细文档，每个文件针对一个后端子系统。

| 文件 | 作用 |
|---|---|
| [backend/docs/README.md](backend/docs/README.md) | 后端文档目录（Quick Links 索引） |
| [backend/docs/ARCHITECTURE.md](backend/docs/ARCHITECTURE.md) | 后端架构总览 |
| [backend/docs/API.md](backend/docs/API.md) | 后端 API 总览 |
| [backend/docs/SETUP.md](backend/docs/SETUP.md) | 后端安装/启动 |
| [backend/docs/CONFIGURATION.md](backend/docs/CONFIGURATION.md) | 后端配置项详解（`config.yaml` 各项） |
| [backend/docs/AUTH_DESIGN.md](backend/docs/AUTH_DESIGN.md) | 鉴权设计（JWT、密码哈希、OIDC） |
| [backend/docs/AUTH_UPGRADE.md](backend/docs/AUTH_UPGRADE.md) | 鉴权升级变更说明 |
| [backend/docs/AUTH_TEST_PLAN.md](backend/docs/AUTH_TEST_PLAN.md) | 鉴权测试计划 |
| [backend/docs/AUTH_TEST_DOCKER_GAP.md](backend/docs/AUTH_TEST_DOCKER_GAP.md) | 鉴权测试在 Docker 场景的覆盖差距 |
| [backend/docs/SSO.md](backend/docs/SSO.md) | SSO / OIDC 集成 |
| [backend/docs/GITHUB_AGENTS.md](backend/docs/GITHUB_AGENTS.md) | GitHub Agent（PR/Issue 自动化） |
| [backend/docs/GUARDRAILS.md](backend/docs/GUARDRAILS.md) | 护栏（敏感操作阻断、工具边界） |
| [backend/docs/MCP_SERVER.md](backend/docs/MCP_SERVER.md) | MCP 服务器实现 |
| [backend/docs/MEMORY_IMPROVEMENTS.md](backend/docs/MEMORY_IMPROVEMENTS.md) | 长期记忆改进（含详细清单） |
| [backend/docs/MEMORY_IMPROVEMENTS_SUMMARY.md](backend/docs/MEMORY_IMPROVEMENTS_SUMMARY.md) | 记忆改进摘要 |
| [backend/docs/MEMORY_SETTINGS_REVIEW.md](backend/docs/MEMORY_SETTINGS_REVIEW.md) | 记忆设置 review |
| [backend/docs/IM_CHANNEL_CONNECTIONS.md](backend/docs/IM_CHANNEL_CONNECTIONS.md) | IM 渠道连接（Telegram/Slack/Discord/飞书/钉钉/微信/企业微信） |
| [backend/docs/AUTO_TITLE_GENERATION.md](backend/docs/AUTO_TITLE_GENERATION.md) | 会话标题自动生成 |
| [backend/docs/TITLE_GENERATION_IMPLEMENTATION.md](backend/docs/TITLE_GENERATION_IMPLEMENTATION.md) | 标题生成实现细节 |
| [backend/docs/BLOCKING_IO_DETECTION.md](backend/docs/BLOCKING_IO_DETECTION.md) | 阻塞 IO 检测（防止阻塞事件循环） |
| [backend/docs/SANDBOX_MEMORY_PROFILING.md](backend/docs/SANDBOX_MEMORY_PROFILING.md) | 沙箱内存剖析 |
| [backend/docs/REPLAY_E2E.md](backend/docs/REPLAY_E2E.md) | E2E 回放（确定性重放测试） |
| [backend/docs/RUN_EVENT_STREAM.md](backend/docs/RUN_EVENT_STREAM.md) | Run 事件流（SSE 流式）契约 |
| [backend/docs/STREAMING.md](backend/docs/STREAMING.md) | 流式输出（前端 SSE 消费） |
| [backend/docs/SUMMARIZATION.md](backend/docs/summarization.md) | 长上下文摘要（自动压缩） |
| [backend/docs/TUI.md](backend/docs/TUI.md) | 终端工作台（Terminal Workbench） |
| [backend/docs/FILE_UPLOAD.md](backend/docs/FILE_UPLOAD.md) | 文件上传后端 |
| [backend/docs/APPLE_CONTAINER.md](backend/docs/APPLE_CONTAINER.md) | Apple Container 部署 |
| [backend/docs/PATH_EXAMPLES.md](backend/docs/PATH_EXAMPLES.md) | 路径配置示例 |
| [backend/docs/PLAN_MODE_USAGE.md](backend/docs/plan_mode_usage.md) | Plan Mode 用法（只读 Agent 模式） |
| [backend/docs/TASK_TOOL_IMPROVEMENTS.md](backend/docs/task_tool_improvements.md) | Task 工具改进 |
| [backend/docs/MIDDLEWARE-EXECUTION-FLOW.md](backend/docs/middleware-execution-flow.md) | 中间件执行流程 |
| [backend/docs/TODO.md](backend/docs/TODO.md) | 后端待办 |
| [backend/docs/rfc-create-tianshu-agent.md](backend/docs/rfc-create-tianshu-agent.md) | RFC：创建 TianShu Agent |
| [backend/docs/rfc-extract-shared-modules.md](backend/docs/rfc-extract-shared-modules.md) | RFC：抽取共享模块 |
| [backend/docs/rfc-grep-glob-tools.md](backend/docs/rfc-grep-glob-tools.md) | RFC：grep/glob 工具 |

> `backend/docs/memory-settings-sample.json` 是后端记忆设置的样本 JSON（不是 md）。

---

## 4. `contracts/` — 接口与协议契约（JSON）

| 文件 | 作用 |
|---|---|
| [contracts/run_event_stream_contract.json](contracts/run_event_stream_contract.json) | Run 事件流契约（前后端共享） |
| [contracts/slash_skill_contract.json](contracts/slash_skill_contract.json) | 斜杠技能契约（`/skill-name` 触发） |
| [contracts/subagent_status_contract.json](contracts/subagent_status_contract.json) | 子智能体状态契约 |
| [contracts/skill_review/package_snapshot.v1.schema.json](contracts/skill_review/package_snapshot.v1.schema.json) | 技能评审：包快照 v1 schema |
| [contracts/skill_review/review_facts.v1.schema.json](contracts/skill_review/review_facts.v1.schema.json) | 技能评审：评审事实 v1 schema |
| [contracts/skill_review/review_report.v1.schema.json](contracts/skill_review/review_report.v1.schema.json) | 技能评审：评审报告 v1 schema |

---

## 5. `frontend/` 内文档

| 文件 | 作用 |
|---|---|
| [frontend/README.md](frontend/README.md) | 前端门面 |
| [frontend/AGENTS.md](frontend/AGENTS.md) | 前端编码 Agent 规则 |
| [frontend/CLAUDE.md](frontend/CLAUDE.md) | Claude Code wrapper（引用 AGENTS.md） |

---

## 6. `deploy/` 内文档

| 文件 | 作用 |
|---|---|
| [deploy/helm/tian-shu/README.md](deploy/helm/tian-shu/README.md) | Helm Chart 部署说明 |
| [docker/lark-cli-broker/README.md](docker/lark-cli-broker/README.md) | Lark CLI Broker 容器 |
| [docker/lark-cli-init/README.md](docker/lark-cli-init/README.md) | Lark CLI Init 容器 |
| [docker/provisioner/README.md](docker/provisioner/README.md) | Provisioner 容器（AIO sandbox） |

---

## 7. 按"我要做什么"快速索引

| 我想做的事 | 看哪里 |
|---|---|
| 看项目是什么、怎么跑起来 | [README.md](README.md) / [README_zh.md](README_zh.md) |
| 新增/调整 Git 集成功能 | [docs/git-integration/](docs/git-integration/) |
| 新增/调整工作空间 / 文件 | [docs/workspace/](docs/workspace/) |
| 新增/调整工作流引擎 | [docs/mutil-agents/](docs/mutil-agents/) |
| 新增/调整用户级 MCP | [docs/user-mcp/](docs/user-mcp/) |
| 新增/调整用户设置（千人千面） | [docs/user-settings/](docs/user-settings/) |
| 查数据库结构 / 种子数据 | [docs/database/](docs/database/) |
| 查后端架构 / API | [backend/docs/ARCHITECTURE.md](backend/docs/ARCHITECTURE.md) / [backend/docs/API.md](backend/docs/API.md) |
| 调整鉴权 | [backend/docs/AUTH_DESIGN.md](backend/docs/AUTH_DESIGN.md) |
| 调整 MCP | [backend/docs/MCP_SERVER.md](backend/docs/MCP_SERVER.md) |
| 调整长期记忆 | [backend/docs/MEMORY_IMPROVEMENTS.md](backend/docs/MEMORY_IMPROVEMENTS.md) |
| 调整 IM 渠道（Telegram/Slack/...） | [backend/docs/IM_CHANNEL_CONNECTIONS.md](backend/docs/IM_CHANNEL_CONNECTIONS.md) |
| 调整 GitHub Agent | [backend/docs/GITHUB_AGENTS.md](backend/docs/GITHUB_AGENTS.md) |
| 调整 SSE 流式 | [backend/docs/RUN_EVENT_STREAM.md](backend/docs/RUN_EVENT_STREAM.md) / [backend/docs/STREAMING.md](backend/docs/STREAMING.md) |
| 调整沙箱 | [backend/docs/SANDBOX_MEMORY_PROFILING.md](backend/docs/SANDBOX_MEMORY_PROFILING.md) |
| 看后端 RFC / 草稿 | [backend/docs/rfc-*.md](backend/docs/) + [plans/](plans/) |
| 看事件/协议契约 | [contracts/](contracts/) |
| 准备发布 / 打 tag | [RELEASING.md](RELEASING.md) |
| 写提交 / PR | [CONTRIBUTING.md](CONTRIBUTING.md) + [AGENTS.md](AGENTS.md) |
| 用 Agent（Trae/Claude Code/Codex）干活 | [AGENTS.md](AGENTS.md) |

---

## 8. 命名与目录约定

- **业务模块**：每个新功能域放 `docs/<module-name>/`，含 `requirements.md / architecture.md / database.md / api.md` + 必要时 `audit-requirements.md`，统一使用 Mermaid 图（业务流程 / 系统架构 / ER / 时序）。
- **后端子系统**：`backend/docs/<topic>.md` 单文件归档。
- **草稿/方案**：`plans/` 或 `backend/docs/rfc-*.md`。
- **协议契约**：`contracts/<topic>/<name>.vN.schema.json` 或 `contracts/<name>_contract.json`。