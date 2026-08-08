# 🦌 TianShu — 多租户超级智能体工作台

> 多租户 · 全隔离 · 企业级智能体工作台

[English](./README.md)

[![Python](https://img.shields.io/badge/Python-3.12%2B-3776AB?logo=python&logoColor=white)](./backend/pyproject.toml)
[![Node.js](https://img.shields.io/badge/Node.js-22%2B-339933?logo=node.js&logoColor=white)](./Makefile)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![Framework](https://img.shields.io/badge/Framework-LangGraph%20%2F%20LangChain-1C3C3C?logo=langchain&logoColor=white)](./backend)

---

TianShu 是**基于 DeerFlow 底层框架（LangGraph + LangChain）迭代而来的商用级二次开发**。在开源超级智能体运行时之上，我们构建了完整的**多租户层**与**个人生产力工作台**：每个用户拥有独立账号、独立数据与独立配置，账号之间完全隔离；同时新增工作流、工作空间、文件、Git 源代码管理、MCP 集成与多模型管理等企业级能力。

---

## 为什么选择 TianShu

大多数智能体框架都是单用户工具。TianShu 从第一天起就为**团队与组织**而生：

- **天生多用户** — 注册即用，你创建的一切数据都归你所有，与他人完全隔离。
- **数据完全隔离** — 工作空间、文件夹、文件、Git 凭证、MCP 工具与模型设置全部按账号隔离，系统绝不泄露其他用户的数据存在性。
- **企业级生产力** — 工作流、工作空间文件夹、文件、Git 源代码管理、MCP 集成与多模型选择，全部内嵌在对话区，知识工作与研发工作在同一个界面完成。
- **成熟底座** — 基于 DeerFlow/TianShu 超级智能体框架：LangGraph + LangChain 编排、子智能体、技能（Skills）、长期记忆、沙箱文件系统与智能体浏览器控制。

## 核心亮点

| 亮点 | 说明 |
|---|---|
| **多租户 · 完全隔离** | 工作空间、设置、Git 令牌、MCP 工具、模型全部按账号隔离；非本人资源返回 `404`，不泄露存在性。 |
| **可视化工作流** | 以 DAG 定义工作流并执行，每一步实时流式展示（运行中 / 成功 / 失败）。 |
| **工作空间 · 文件夹 · 文件** | 每人一套三级空间；会话可绑定文件夹，将文档载入上下文并回写归档结果。 |
| **Git 源代码管理** | 任意文件夹可绑定 GitHub / Gitee 仓库，支持拉取（clone / ff-only）与推送，SSE 实时日志。 |
| **MCP 集成** | 按用户注册 MCP 服务器（stdio / SSE / HTTP），运行时按用户解析并注入工具。 |
| **多模型管理** | 按账号配置模型列表、会话内切换模型，配额耗尽自动降级回退。 |
| **一体化会话工具栏** | 工作空间绑定、Git、MCP、工作流、模型选择，全部在输入框内一键触达。 |

## 核心能力

### 多租户架构与完全数据隔离

- **身份无处不在** — 每个请求都通过 `get_effective_user_id()` 解析调用者身份，所有数据查询均按此过滤。
- **零跨用户泄露** — 不属于调用者的资源一律返回 `404`，接口从不暴露其他用户资源是否存在。
- **Git 凭证按账号隔离** — 个人访问令牌按账号存储，接口仅返回 `configured` 掩码，绝不回显明文。
- **MCP 工具按用户隔离** — 每个账号决定继承哪些 MCP 服务器的工具，运行时计算并注入生效工具集。
- **模型设置按用户隔离** — 每个账号独立配置自己的模型，互不影响。

### 超级智能体引擎

- **子智能体** — 主智能体可规划并派生子智能体处理复杂多步任务。
- **可扩展技能** — 技能渐进加载、`/技能名` 斜杠激活，支持自定义 `SKILL.md` 技能包。
- **长期记忆** — 跨会话持久记忆，支持个性化、连续的工作。
- **沙箱与文件系统** — 沙箱化执行、托管文件系统、bash 与浏览器控制。

### 可视化工作流编排

- 以**节点 + 边（DAG）** 定义工作流，支持创建、编辑、校验、复制与删除。
- 内置引擎执行工作流，通过 **SSE 实时事件**（运行中 / 成功 / 失败）流式回传对话区。
- 查看分步执行详情、重新运行工作流 — 告别"发起后不可见"。

### 工作空间 · 文件夹 · 文件

- 每位用户拥有三级层级：**工作空间 → 工作空间文件夹 → 文件**。
- 文件为 Markdown 文档，带体积上限保护。
- **会话绑定工作空间文件夹** — 将文档载入对话上下文，并将会话产出回写归档至文件夹，跨消息持久保留。

### Git 源代码管理

- **文件夹 ↔ 仓库绑定** — 任意工作空间文件夹可绑定 GitHub / Gitee 仓库（URL 校验、`.git` 后缀归一化）。
- **拉取** — 首次自动 clone，之后仅 fast-forward 拉取，磁盘 ↔ 数据库双向同步，保证文件树一致。
- **推送** — 一键提交并推送本地变更；推送失败绝不污染数据库。
- **实时操作面板** — 拉取 / 推送以 SSE 流式输出命令日志，在对话区内面板实时展示。
- **按账号设置** — 在设置中配置 GitHub / Gitee 令牌，附「如何获取令牌？」分步帮助卡片。

### MCP 集成

- **用户自管服务器注册** — 每个账号经 `/api/user/mcp` 注册并管理自己的 MCP 服务器（stdio / SSE / HTTP 三种传输）。
- **全局配置不进用户会话** — 系统全局 MCP 配置永不进入用户聊天，用户注册表是唯一运行时工具来源。
- **会话内工具菜单** — 在输入区直接查看与开关你的 MCP 工具。

### 多模型管理

- **按账号模型列表** — 在设置中配置 Provider、模型名、API Key 与 Base URL。
- **会话内切换模型** — 随时切换当前会话模型，并尊重自定义智能体的默认模型。
- **自动降级回退** — 某 Provider 配额耗尽（如错误码 2056）时，运行时自动切换到其他已配置模型，对话不中断。

### 一体化会话工具栏

所有能力都在输入区一键触达：

- **工作空间绑定** — 选择文件夹，其文档载入对话上下文，产出回写归档。
- **Git** — 对绑定文件夹执行拉取 / 推送，SSE 实时日志。
- **MCP** — 打开 MCP 工具菜单。
- **工作流** — 在输入区选择并执行工作流。
- **模型选择** — 不离开对话即可切换当前模型。

## 架构总览

```mermaid
flowchart LR
  subgraph Clients["客户端"]
    Web["Web 控制台 (Next.js)"]
  end

  subgraph Gateway["API 网关 (FastAPI)"]
    Auth["认证与租户上下文"]
    WF["工作流引擎"]
    Git["Git 服务"]
    MCP["MCP 运行时"]
  end

  subgraph Agent["超级智能体运行时 (LangGraph + LangChain)"]
    Lead["主智能体"]
    Subs["子智能体"]
    Mem["长期记忆"]
    Sandbox["沙箱与文件"]
  end

  subgraph Data["数据与外部"]
    PG[("PostgreSQL")]
    Repos["Git 仓库 (GitHub / Gitee)"]
    MCPs["MCP 服务器"]
    LLMs["模型服务 (MiniMax / DeepSeek / ...)"]
  end

  Web --> Gateway
  Gateway --> Agent
  Gateway --> PG
  Agent --> PG
  Agent --> Repos
  Gateway --> MCPs
  Agent --> LLMs
```

## 技术栈

| 分层 | 技术 |
|---|---|
| 后端 | Python 3.12+ · FastAPI · LangGraph · LangChain |
| 前端 | Next.js 16 · React · TypeScript · Tailwind CSS · Radix UI |
| 数据库 | PostgreSQL（异步 SQLAlchemy） |
| 模型服务 | MiniMax（M3 / M2.7）· DeepSeek（v4 flash / v4 pro）· OpenAI 兼容网关 |
| 集成 | MCP（stdio / SSE / HTTP）· GitHub 与 Gitee Git · 联网搜索 / 抓取 |
| 部署 | Docker Compose · Nginx · uv · pnpm |

## 典型应用场景

- **团队知识工作** — 每个成员拥有私有工作空间、文件夹与文档；将文件夹绑定到对话，让智能体基于你的内容作答。
- **AI 辅助研发** — 将工作空间文件夹连接 Git 仓库，拉取最新代码 → 智能体修改 → 一键推送，全程在一个对话内完成。
- **自动化工作流** — 运行 DAG 工作流完成调研、报告、代码生成或内容生产，实时查看进度。
- **受控工具开放** — 只给团队成员分配其所需的 MCP 服务器与模型。

## 快速开始

### 环境要求

- Python 3.12+、Node.js 22+、`uv`、`pnpm`
- PostgreSQL（默认 `postgresql://postgres:postgres@localhost:5432/tianshu`，可在 `config.yaml` 中修改）

### 1. 克隆并安装

```bash
git clone <your-repo-url> && cd <your-repo>
make install
```

或手动安装：后端 `cd backend && uv sync`，前端 `frontend/` 下 `python scripts/pnpm.py install`。

### 2. 配置

```bash
make setup     # 交互式向导：模型服务商、联网搜索、沙箱、安全策略
make doctor    # 校验配置并给出修复建议
```

向导会生成 `config.yaml` 并把 API Key 写入 `.env`。模型按服务商分别配置（如 MiniMax、DeepSeek）；建议开启**模型自动降级回退**，配额耗尽时对话不中断。

### 3. 启动

```bash
make dev                      # 本地开发（热更新）
# 或
make docker-init && make docker-start   # Docker（持久化服务器推荐）
```

### 4. 首次登录

打开 `http://localhost:3000`，创建管理员账号，然后邀请 / 注册其他用户——每个账号都是独立租户。

## 安全

- 数据层强制按调用者身份隔离：所有查询均以用户身份过滤。
- Git 令牌按账号存储，接口永不回显（仅返回 `configured` 掩码）。
- 系统全局 MCP 配置绝不进入用户会话。
- 生产部署请遵循上游文档的安全建议：HTTPS 终止、限制沙箱、最小权限账号。

## 许可证与支持

本项目是**基于开源 DeerFlow 项目（https://github.com/bytedance/tian-shu）的二次开发**。上游 DeerFlow 代码遵循 [MIT License](./LICENSE)；本仓库 TianShu 特有的修改与新增部分按 [LICENSE](./LICENSE) 中的附加条款发布，**仅限个人学习与非商业用途**。

- ✅ 个人学习、研究、非商业评估：**允许**。
- ❌ 商业使用：**未经 TianShu 作者书面许可，禁止**。

如需商业授权、部署支持或企业级服务，请提交 Issue 或联系维护团队。
