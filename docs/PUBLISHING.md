# 发布到 Git 仓库 — 文档路由与发布指南

> 目的：把本仓库（基于 DeerFlow 的 TianShu 二开）发布到 Git 时，**哪些文件/文件夹可以不上传**，以及发布前的检查清单。
> 适用：把仓库推到 GitHub / Gitee / GitLab 等任何 Git 远端。

---

## 1. 发布原则

发布出去的代码必须：

1. **可被任意协作者 clone + make setup + make dev 跑起来**。
2. **不携带任何机器本地状态**（用户专属配置、本机日志、IDE 工作区）。
3. **不泄露任何密钥或凭证**（API Key、PAT、JWT secret、数据库 DSN 含密码等）。
4. **保留示例与文档**，让新协作者能理解项目结构（`config.example.yaml`、`quick-start.env`、`.env.example`、`*.example.json` 等）。

`.gitignore` 是**强制**的——一旦发布，本仓库 `git ls-files` 之外的内容不会公开。

---

## 2. 上传时应排除的文件 / 文件夹（必读）

### 2.1 顶层本机状态（不会推、也不应推）

| 路径 | 性质 | 为什么不上传 |
|---|---|---|
| `.agent/` | Trae agent skills 缓存 | 本机 IDE 状态，无公共价值 |
| `.trae/` | Trae IDE 状态（含 `.trae/memory/logs.md` 等会话日志 + e2e 临时附件） | 本机 Agent 会话历史，可能含个人偏好/账号信息 |
| `.ruff_cache/` | ruff lint 缓存 | 自动生成、可重建 |
| `.run-logs/` | quick-start.ps1 启动日志 | 本机运行时输出 |
| `.tian-shu/` | 项目运行时 SQLite 与用户文件残留（早期 SQLite 文件） | 历史残留，运行时不引用；当前 PostgreSQL 才是真正数据库 |
| `.pnpm-store/` | pnpm 本地 store | 自动下载、可重建（每个协作者 `pnpm install` 自己下） |
| `.git/` | git 自身 | 由 git 管理 |
| `tian-shu.code-workspace` | 单开发者 IDE 工作区文件（路径绑定本机） | 路径与个人习惯绑定，不适合共享 |

### 2.2 凭据与配置（绝不上传）

| 路径 | 性质 | 为什么不上传 |
|---|---|---|
| `.env` | 真实 API Key / DSN / 密码 | **含密钥** |
| `config.yaml` | 个人定制配置（含 `MINIMAX_API_KEY=$MINIMAX_API_KEY` 等 `database.postgres_url`、模型 key） | 含机器本地地址/账号密码 |
| `quick-start.env` | 一键启动脚本使用的本机环境变量 | 可能含本机路径与密钥 |
| `mcp_config.json` / `extensions_config.json` | 工具/MCP 私有配置 | 个人配置 |
| `*.local` | 各种 IDE 本地配置 | 个人 |

> ✅ 上传示例：`config.example.yaml`、`quick-start.env`（注意 `quick-start.env` 是示例文件，安全时上传；具体以项目结构为准）、`.env.example`、`extensions_config.example.json`。

### 2.3 Python / Node 缓存与虚拟环境

| 路径 | 性质 |
|---|---|
| `.venv/` / `venv/` | Python 虚拟环境（每个协作者 `uv sync` 自建） |
| `__pycache__/`、`*.pyc`、`*.pyo` | Python 字节码 |
| `node_modules/` | Node 依赖（每个协作者 `pnpm install` 自建） |
| `frontend/test-results/`、`frontend/playwright-report/` | Playwright 测试产物 |
| `backend/.venv/` 等子项目 venv | 同上 |

### 2.4 构建产物与运行数据

| 路径 | 性质 |
|---|---|
| `docker/.cache/` | Docker 构建缓存 |
| `sandbox_image_cache.tar` | 沙箱镜像缓存 |
| `bench_results.jsonl` / `bench_optimized.jsonl` / `results.jsonl` | benchmark 输出 |
| `backend/scripts/benchmark/*.jsonl` | benchmark 输出 |
| `coverage.xml` / `coverage/` | 覆盖率报告 |
| `logs/` / `log/` / `debug.log` | 运行日志 |
| `backend/data/tiansu.db` | 早期 SQLite 文件（拼写错误 `tiansu`，早期本地使用） |
| `.monocle/` | Monocle 追踪输出 |
| `.omc/` | oh-my-claudecode 状态 |
| `.playwright-mcp` | Playwright MCP 缓存 |
| `.gstack/` | gstack 状态 |
| `.worktrees` | git worktree 临时目录 |
| `backend/Dockerfile.langgraph` | 本地构建产物 |
| `config.yaml.bak` | 配置备份 |
| `web/` | 遗留前端目录（已弃用） |

### 2.5 IDE 状态

| 路径 | 性质 |
|---|---|
| `.idea/` | JetBrains IDE |
| `.vscode/` | VS Code |
| `.claude/` | Claude Code 状态 |
| `.githooks/` | 本机 git hooks（不共享） |
| `*.swp`、`.DS_Store`、`Thumbs.db` 等 OS 文件 | 系统垃圾 |

### 2.6 数据库运行时数据（当前 PostgreSQL 后端的数据是远端数据库，不在此仓库）

> ⚠️ 本仓库**不携带**任何数据库 dump。数据库连接字符串只放在协作者本机的 `config.yaml`（被 `.gitignore` 排除）。
>
> 协作者 clone 后需自己准备 PostgreSQL 实例并填入 `database.postgres_url`。`docs/database/active-tianshu-seed.sql` 提供种子数据 SQL，**应作为示例被发布**。

### 2.7 旧版 SQLite 文件夹

| 路径 | 性质 |
|---|---|
| `backend/.tian-shu/` | 早期 SQLite 用户文件残留（含 `data/tianshu.db` + WAL/SHM） |

> 不进 git。`.tian-shu/` 已在 `.gitignore` 中被忽略。

---

## 3. `.gitignore` 当前覆盖范围（速查）

完整文件：[.gitignore](../.gitignore)（共 94 行，分组注释）。覆盖规则：

- 缓存：`__pycache__/`、`*.pyc`、`*.pyo`、`.ruff_cache/`
- 虚拟环境：`.venv/`、`venv/`
- 环境与密钥：`.env`、`config.yaml`、`mcp_config.json`、`extensions_config.json`、`quick-start.env`、`*.local`
- 运行时数据：`.tian-shu/`、`.claude/`、`logs/`、`log/`、`debug.log`、`.tian-shu.code-workspace`
- 工具缓存：`.pnpm-store/`、`sandbox_image_cache.tar`、`docker/.cache/`、`.omc/`、`.playwright-mcp`、`.gstack/`、`.worktrees`、`.monocle/`
- 构建/测试产物：`bench_results.jsonl`、`coverage.xml`、`/frontend/test-results/`、`/frontend/playwright-report/`、`backend/Dockerfile.langgraph`、`config.yaml.bak`、`web/`
- 本机 Agent/IDE 状态：`.agent/`、`.trae/`、`.run-logs/`
- IDE / OS：`.idea/`、`.vscode/`、`.githooks/`、`.DS_Store`、`Thumbs.db`、`ehthumbs.db`、`*.swp`
- 报告与定制：`backend/scripts/benchmark/*.jsonl`、`skills/custom/*`

---

## 4. 发布前 Checklist

按顺序执行，最后再 `git push`：

### 4.1 清理本机残留（不要带上去）

```bash
# 在仓库根目录执行
cd e:\QClaw\DeerFlow

# 1. 删除本机 SQLite 历史残留（注意：会丢失旧 SQLite 用户数据，确认无价值后再执行）
rm -rf .tian-shu backend/.tian-shu backend/data/tiansu.db

# 2. 删除本机配置文件（将 config.yaml / .env 还原为 .example 模板）
rm -f config.yaml .env quick-start.env
# 之后让协作者执行 make setup 重新生成

# 3. 删除 IDE 与 Agent 状态
rm -rf .agent .trae .ruff_cache .run-logs tian-shu.code-workspace

# 4. 删除构建缓存
rm -rf .pnpm-store docker/.cache *.tar
```

### 4.2 核对 `.gitignore`

```bash
git check-ignore -v config.yaml .env quick-start.env .tian-shu/ .trae/ .agent/ .pnpm-store/ .ruff_cache/ tian-shu.code-workspace
```

所有路径必须显示"被 .gitignore 忽略"。

### 4.3 确认示例与文档齐全

确保以下文件**存在且会被跟踪**：

- `config.example.yaml`（不带真实密钥）
- `.env.example`
- `quick-start.env`（如果是示例模板）或在 `quick-start.ps1` 注释里说明
- `extensions_config.example.json`
- `LICENSE`
- `README.md`、`README_zh.md`
- `DOCS_ROUTING.md`
- `docs/` 下完整专题文档（git-integration / workspace / mutil-agents / user-mcp / user-settings / database）
- `CHANGELOG.md`、`CHANGELOG_zh.md`
- `CONTRIBUTING.md`、`CODE_OF_CONDUCT.md`、`SECURITY.md`、`RELEASING.md`
- `backend/`、`frontend/`、`contracts/`、`deploy/`、`docker/`、`skills/`、`scripts/`、`tests/`、`plans/`

### 4.4 验证无密钥残留

```bash
# 防止误提交密钥
git grep -nIE 'sk-[A-Za-z0-9]{20,}'   # DeepSeek / OpenAI 风格
git grep -nIE 'ghp_[A-Za-z0-9]{20,}'  # GitHub PAT
git grep -nIE 'glpat-[A-Za-z0-9_-]{20,}'  # GitLab PAT
git grep -nIE 'password\s*[:=]\s*['\''\"]?\w+' -i
git grep -nIE 'postgres://[^:]+:[^@]+@'   # 含密码的 DSN
```

任何命中必须删除或抽象到环境变量。

### 4.5 初始化 Git 与首次推送

```bash
cd e:\QClaw\DeerFlow
git init
git branch -M main
git add .
git status        # 复核待提交文件清单
git commit -m "feat: initial public release of TianShu (secondary development on DeerFlow)"
git remote add origin https://github.com/<your-org>/<your-repo>.git
git push -u origin main
```

### 4.6 设置 GitHub / Gitee 仓库元数据

- **Description**：`TianShu — Multi-Tenant Super-Agent Workbench (secondary development on DeerFlow)`
- **Topics / Tags**：`agent-framework`、`multi-tenant`、`deerflow`、`tianshu`、`langgraph`、`langchain`、`workflow`、`mcp`、`self-hosted`、`personal-workspace`
- **License**：MIT for upstream DeerFlow portions + TianShu additional terms（已在 LICENSE 中说明）
- **README badges**：Python / Node.js / License / Framework（参考现有 README.md 顶部）

### 4.7 启用仓库保护（可选但强烈建议）

- 开启 PR 流程（contributors fork → PR）
- 启用 CODEOWNERS（核心目录维护者审阅）
- 启用 Required Status Checks（CI 通过才合并）
- 启用 Signed Commits

---

## 5. 协作者首次接入步骤（写在 CONTRIBUTING.md）

将以下内容合并到 [CONTRIBUTING.md](../CONTRIBUTING.md) 的"本地开发"章节，让协作者无歧义：

1. `git clone <repo>` 后进入目录
2. 复制 `config.example.yaml` 为 `config.yaml`，按需填写数据库 DSN / 模型 key
3. 复制 `.env.example` 为 `.env`，写入实际 API key
4. `make install`（拉依赖）
5. `make setup`（交互式配置向导）
6. `make doctor`（健康检查）
7. `make dev` 或 `make docker-start`

> ⚠️ 协作者需自备 PostgreSQL 实例（默认 `postgresql://postgres:postgres@localhost:5432/tianshu`，可在 `config.yaml` 中修改）。如需初始化种子数据，可参考 [docs/database/active-tianshu-seed.sql](database/active-tianshu-seed.sql)。

---

## 6. 发布后维护

- **每个 release**：按 [RELEASING.md](../RELEASING.md) 打 tag（tag 触发发布）。
- **CHANGELOG**：每个 PR 累积到 [CHANGELOG.md](../CHANGELOG.md) 与 [CHANGELOG_zh.md](../CHANGELOG_zh.md) 的 `## [Unreleased]`。
- **SECURITY 漏洞上报**：通过 [SECURITY.md](../SECURITY.md) 流程。

---

## 7. 一句话总览

> **上传：代码、文档、示例配置、契约、测试夹具、静态资源、CI 配置、合约。**
> **不上传：本地 SQLite / pnpm store / venv / API key / 个人配置 / IDE 工作区 / 任何机器路径。**
>
> 拿不准时优先看 [.gitignore](../.gitignore) 与本文件的"2. 上传时应排除"清单。

---

## 8. 本次发布（2026-08-08）的补充

本次发版相对 `.gitignore` 历史版本新增了以下规则（见 [git diff](file:///e:/QClaw/DeerFlow/.gitignore)）：

- `.agent/`、`.trae/`、`.ruff_cache/`、`.run-logs/`、`tian-shu.code-workspace`、`quick-start.env`、`config.yaml` 已显式排除（其中后两者此前为隐式忽略）。
- LICENSE 已重写，明确"上游 DeerFlow MIT + TianShu 二开附加条款（仅限个人学习、非商业）"。

发布前请务必按 §4.1 执行清理；如发现 `git check-ignore` 中有任何路径未被忽略，立即补充规则再 `git add`。