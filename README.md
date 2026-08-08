# 🦌 TianShu — Multi-Tenant Super-Agent Workbench

> Multi-Tenant · Fully Isolated · Enterprise Agent Workbench

[中文](./README_zh.md)

[![Python](https://img.shields.io/badge/Python-3.12%2B-3776AB?logo=python&logoColor=white)](./backend/pyproject.toml)
[![Node.js](https://img.shields.io/badge/Node.js-22%2B-339933?logo=node.js&logoColor=white)](./Makefile)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![Framework](https://img.shields.io/badge/Framework-LangGraph%20%2F%20LangChain-1C3C3C?logo=langchain&logoColor=white)](./backend)

---

TianShu is a **commercial-grade secondary development built on the DeerFlow base framework (LangGraph + LangChain)**. On top of the open-source super-agent runtime, we built a complete **multi-tenant layer** and a **personal productivity workbench**: every user gets their own account, their own data, and their own settings — fully isolated from one another — plus enterprise capabilities including workflows, workspaces, files, Git source-code management, MCP integration, and multi-model management.

---

## Why TianShu

Most agent frameworks are single-user tools. TianShu is built for **teams and organizations** from day one:

- **Multi-user by design** — register an account, log in, and everything you create belongs to you and only you.
- **Complete data isolation** — workspaces, folders, files, Git credentials, MCP tools, and model settings are all scoped per account. The system never leaks another user's existence or data.
- **Enterprise productivity** — workflows, workspace folders, files, Git source management, MCP integration, and multi-model selection live right inside the conversation, so knowledge work and software work happen in one place.
- **Built on a proven base** — powered by the DeerFlow/TianShu super-agent harness: LangGraph + LangChain orchestration, sub-agents, skills, long-term memory, sandboxed file system, and agentic browser control.

## Key Highlights

| Highlight | What it means |
|---|---|
| **Multi-Tenant & Full Isolation** | Per-account workspaces, settings, Git tokens, MCP tools, and models. Non-owned resources return `404` — no existence leak. |
| **Visual Workflows** | Define DAG-style workflows, execute them, and watch every step stream live (running / success / failed). |
| **Workspaces · Folders · Files** | Three-level personal space per user; bind a conversation to a folder to load documents into context and archive outcomes back. |
| **Git Source Management** | Bind any folder to GitHub / Gitee; pull (clone / ff-only) and push with real-time SSE logs. |
| **MCP Integration** | Per-user MCP server registry (stdio / SSE / HTTP); tools resolved and injected per user at run time. |
| **Multi-Model** | Per-user model lists, in-chat model switching, and automatic fallback when a provider's quota runs out. |
| **All-in-One Conversation Toolbar** | Workspace binding, Git, MCP, workflow, and model selectors — right where you type. |

## Core Capabilities

### Multi-Tenant Architecture & Full Data Isolation

- **Identity is everywhere** — every request resolves the caller through `get_effective_user_id()`, and every repository query is filtered by it.
- **No cross-user leakage** — resources that do not belong to the caller resolve to `404`; the API never reveals whether another user's resource exists.
- **Per-user Git credentials** — personal access tokens are stored per account; the API only returns a `configured` mask and never echoes the token.
- **Per-user MCP tools** — each account decides which MCP servers' tools it inherits; the effective toolset is computed and injected at run time.
- **Per-user model settings** — each account configures its own models, independent of every other user.

### Super-Agent Engine

- **Sub-agents** — the lead agent plans and spawns sub-agents for complex, multi-step tasks.
- **Extensible skills** — progressive loading, slash activation (`/skill-name`), and your own `SKILL.md` packages.
- **Long-term memory** — persistent memory across sessions for personalized, continuous work.
- **Sandbox & file system** — sandbox-aware execution with a managed file system, bash, and browser control.

### Visual Workflow Orchestration

- Create, edit, validate, copy, and delete workflow definitions modeled as a **DAG of nodes and edges**.
- Execute workflows with a built-in engine that streams **real-time SSE events** (running / success / failed) into the conversation.
- Inspect per-step execution details and re-run workflows — no more blind "fire and forget".

### Workspaces · Folders · Files

- A three-level hierarchy owned by each user: **Workspace → Workspace Folder → File**.
- Files are Markdown documents with enforced size limits.
- **Bind a conversation to a workspace folder** — load its documents into the chat context and archive conversation outcomes back into the folder, persisting across messages.

### Git Source-Code Management

- **Folder ↔ repository binding** — bind any workspace folder to a GitHub or Gitee repository (URL validated, `.git` suffix normalized).
- **Pull** — clone on first use, fast-forward-only pulls afterwards, with bidirectional disk ↔ database sync.
- **Push** — commit and push local changes in one action; failed pushes never corrupt the database.
- **Live operation panel** — pull/push run as SSE streams with real-time command logs in a panel inside the conversation.
- **Per-account settings** — configure GitHub / Gitee personal access tokens with step-by-step "How do I get a token?" help cards.

### MCP Integration

- **User-managed server registry** — each account registers and manages its own MCP servers (stdio / SSE / HTTP transports).
- **No global leak into user chats** — system-global MCP config never enters a user session; the user's own registry is the only runtime tool source.
- **In-conversation tools menu** — inspect and toggle your MCP tools right from the chat composer.

### Multi-Model Management

- **Per-user model lists** — configure provider, model name, API key, and base URL in Settings.
- **In-chat model selection** — switch the active model per conversation; custom-agent default models are honored.
- **Automatic fallback** — when a provider's API key quota is exhausted (e.g. error 2056), the runtime automatically downgrades and switches to another configured model.

### All-in-One Conversation Toolbar

Everything is one click away from where you type:

- **Workspace binding** — pick a folder; its documents load into the chat context and outcomes archive back.
- **Git** — pull / push the bound folder with live SSE logs.
- **MCP** — open the MCP tools menu.
- **Workflow** — pick and execute a workflow from the composer.
- **Model selector** — switch the active model without leaving the chat.

## Architecture Overview

```mermaid
flowchart LR
  subgraph Clients["Clients"]
    Web["Web Console (Next.js)"]
  end

  subgraph Gateway["API Gateway (FastAPI)"]
    Auth["Auth & Tenant Context"]
    WF["Workflow Engine"]
    Git["Git Service"]
    MCP["MCP Runtime"]
  end

  subgraph Agent["Super-Agent Runtime (LangGraph + LangChain)"]
    Lead["Lead Agent"]
    Subs["Sub-Agents"]
    Mem["Long-Term Memory"]
    Sandbox["Sandbox & Files"]
  end

  subgraph Data["Data & External"]
    PG[("PostgreSQL")]
    Repos["Git Repos (GitHub / Gitee)"]
    MCPs["MCP Servers"]
    LLMs["LLM Providers (MiniMax / DeepSeek / ...)"]
  end

  Web --> Gateway
  Gateway --> Agent
  Gateway --> PG
  Agent --> PG
  Agent --> Repos
  Gateway --> MCPs
  Agent --> LLMs
```

## Technology Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12+ · FastAPI · LangGraph · LangChain |
| Frontend | Next.js 16 · React · TypeScript · Tailwind CSS · Radix UI |
| Database | PostgreSQL (async SQLAlchemy) |
| LLM Providers | MiniMax (M3 / M2.7) · DeepSeek (v4 flash / v4 pro) · OpenAI-compatible gateways |
| Integration | MCP (stdio / SSE / HTTP) · GitHub & Gitee Git · Web search / fetch |
| Deployment | Docker Compose · Nginx · uv · pnpm |

## Typical Use Cases

- **Team knowledge work** — each member keeps private workspaces, folders, and documents; bind a folder to a chat to ground answers in your own content.
- **AI-assisted development** — connect a workspace folder to a Git repository, pull latest code, ask the agent to modify it, and push back — all inside one conversation.
- **Automated workflows** — run DAG workflows for research, reporting, code generation, or content pipelines with live progress.
- **Controlled tool exposure** — give each team member only the MCP servers and models they need.

## Quick Start

### Prerequisites

- Python 3.12+, Node.js 22+, `uv`, `pnpm`
- PostgreSQL (default `postgresql://postgres:postgres@localhost:5432/tianshu`, configurable in `config.yaml`)

### 1. Clone & install

```bash
git clone <your-repo-url> && cd <your-repo>
make install
```

Or manually: `cd backend && uv sync` and `python scripts/pnpm.py install` in `frontend/`.

### 2. Configure

```bash
make setup     # interactive wizard: model providers, search, sandbox, safety
make doctor    # verify your setup and get actionable fix hints
```

The wizard generates `config.yaml` and writes API keys to `.env`. Models are configured with per-provider entries (e.g. MiniMax, DeepSeek); enable `model fallback` so conversations continue when a quota is exhausted.

### 3. Run

```bash
make dev                      # local development (hot-reload)
# or
make docker-init && make docker-start   # Docker (recommended for persistent servers)
```

### 4. First login

Open `http://localhost:3000`, create your administrator account, then invite/register users — each account is an isolated tenant.

## Security

- Per-account data isolation enforced at the data layer: every query is scoped by the caller's identity.
- Git tokens are stored per account and never returned by the API (only a `configured` mask).
- System-global MCP configuration never enters user sessions.
- For production deployment, follow the security recommendations in the original upstream documentation: HTTPS termination, restricted sandbox, and least-privilege accounts.

## License & Support

This project is a **secondary development built on top of the open-source DeerFlow project**
(https://github.com/bytedance/tian-shu). The upstream DeerFlow code is licensed under the
[MIT License](./LICENSE); the TianShu-specific modifications are released for **personal
learning and non-commercial use only** under the additional terms stated in [LICENSE](./LICENSE).

- ✅ Personal learning, research, and non-commercial evaluation: **allowed**.
- ❌ Commercial use: **NOT allowed** without prior written permission from the TianShu authors.

For commercial licensing, deployment assistance, or enterprise support, please open an issue
or contact the maintainers.
