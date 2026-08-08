# Database — Active Backend & Seed Data

> 最后校对：2026-08-08

## 结论

项目**当前唯一使用的数据库**是本地 PostgreSQL：

| 项 | 值 |
|---|---|
| **DSN** | `postgresql://postgres:postgres@localhost:5432/tianshu` |
| **应用 schema** | `tianshu` |
| **记忆 schema** | `tianshu_memory`（DeerMem 持久化） |
| **配置项** | `database.backend: postgres`（[config.yaml](file:///e:/QClaw/DeerFlow/config.yaml#L254-L259)） |
| **checkpoint 库** | 同 PostgreSQL（LangGraph checkpointer，`tianshu.checkpoints` 等） |

任何"SQLite 文件"都是历史残留或本地开发兜底，**不是当前运行时使用的数据库**。

## 为什么会出现"很多数据库"

排查后发现存在以下**多个 SQLite 文件**，但都**不参与当前 PostgreSQL 后端的运行时**：

| SQLite 文件 | 大小 | 状态 |
|---|---|---|
| `e:\QClaw\DeerFlow\.tian-shu\data\tianshu.db` | 180 KB | 项目根目录下的早期 SQLite 文件残留 |
| `e:\QClaw\DeerFlow\backend\.tian-shu\data\tianshu.db` (+ `-wal`/`-shm`) | 20 MB（+ WAL/SHM） | 早期 SQLite 文件残留（含旧用户数据） |
| `e:\QClaw\DeerFlow\backend\data\tiansu.db` | 385 KB | `check_db.py` 引用的旧 SQLite，文件名拼写是 `tiansu` 而非 `tianshu` |

**为何产生**：项目源码同时兼容 SQLite 与 PostgreSQL（[config.example.yaml](file:///e:/QClaw/DeerFlow/config.example.yaml) 默认 sqlite，postgres 可选）。早期本地开发使用 SQLite，之后切换 PostgreSQL 后这些文件未清理。

## 运行时实际读取的数据库

来自 [config.yaml](file:///e:/QClaw/DeerFlow/config.yaml)：
```yaml
database:
  backend: postgres
  postgres_url: postgresql://postgres:postgres@localhost:5432/tianshu
  postgres_schema: tianshu
```

代码侧确认：`[backend/packages/harness/tianshu/config/database_config.py](file:///e:/QClaw/DeerFlow/backend/packages/harness/tianshu/config/database_config.py)` 与所有 `persistence/*/sql.py` 仓储层都从 `get_app_config().database` 取值，没有旁路直读 SQLite。

## PostgreSQL 数据库清单（实际连接）

连接 [postgresql://postgres:postgres@localhost:5432/tianshu](postgres://postgres:postgres@localhost:5432/tianshu) 后看到 8 个 schema，其中只有 `tianshu` 与 `tianshu_memory` 是活跃数据：

| Schema | 角色 | 表数 | 行数（有数据的表） |
|---|---|---|---|
| **tianshu** | 应用主库（活跃） | 31 | 28 users, 16 agents, 13 workspaces, 13 folders, 23 files, 1 workflow + 4 nodes + 3 edges, 9 executions, 2 user_models, 6 user_settings |
| **tianshu_memory** | 长期记忆（DeerMem） | 2 | 2 memory_documents, 20 memory_facts |
| **public** | 默认 schema | 31 | 仅 `alembic_version=1` 有数据，应用全部 0 行 |
| diag_19684144 | 历史测试残留 | 4 | checkpoints=1（其余 0） |
| pgtest_515bc0b0acc4 | 历史测试残留 | 17 | 仅 alembic_version=1（其余 0） |
| pgtest_79e85b84050e | 历史测试残留 | 17 | alembic_version=1, channel_connections=1（其余 0） |
| pgtest_969d6dbecd70 | 历史测试残留 | 0 | 空 |
| pgtest_bc26158abbfe | 历史测试残留 | 17 | 仅 alembic_version=1（其余 0） |
| pgtest_debug_abc | 历史测试残留 | 17 | 仅 alembic_version=1（其余 0） |

> 说明：5 个 `pgtest_*` schema 是早期调试/测试时反复重建的产物，可以 DROP 清理；`public` 是 Postgres 默认 schema（应用未使用，但被 Alembic 创建了空表）。

## 种子数据提取

已落盘到本目录：

| 文件 | 大小 | 内容 |
|---|---|---|
| [active-tianshu-schema.sql](file:///e:/QClaw/DeerFlow/docs/database/active-tianshu-schema.sql) | 15 KB | `tianshu` schema 下 31 张表的完整 CREATE TABLE（含 PK / UNIQUE / FK） |
| [active-tianshu-seed.sql](file:///e:/QClaw/DeerFlow/docs/database/active-tianshu-seed.sql) | 64 KB | 种子表的 INSERT 语句（users, user_settings, user_models, agents, workflows/nodes/edges/executions, user_workspaces, workspace_folders, workspace_files） |

**排除的运行时表**（不参与种子数据）：`alembic_version`、`checkpoint_*`、`runs`、`run_events`、`scheduled_task_runs`、`threads_meta`、`feedback`、`channel_*`、`webhook_deliveries`、`store*`。

## 提取方式

```bash
# 后端 venv
cd e:\QClaw\DeerFlow\backend
uv run python ../temp/dump_seed.py
```

工具脚本：[temp/dump_seed.py](file:///e:/QClaw/DeerFlow/temp/dump_seed.py)（自构 DDL，无需 `pg_dump` / `pg_get_tabledef`）。

## 种子数据一览（活跃 `tianshu` schema）

| 表 | 行数 | 备注 |
|---|---|---|
| users | 28 | 1 个 admin（`60d7060c-...`）+ 1 个真实用户（`3e610d8b-...`，`1033085514@qq.com`）+ 26 个 E2E 测试用户 |
| user_settings | 6 | `appearance / channels / integrations / tools / git` 各类 |
| user_models | 2 | 用户级模型列表 |
| agents | 16 | 默认 + 用户自建 |
| workflows | 1 | |
| workflow_nodes | 4 | |
| workflow_edges | 3 | |
| workflow_executions | 9 | |
| workflow_execution_steps | 0 | |
| user_workspaces | 13 | |
| workspace_folders | 13 | |
| workspace_files | 23 | Markdown 文档 |
| user_mcp | 0 | 用户级 MCP（注册表已建，本期未启用） |

> `agents` 中含 `researcher / analyst / writer` 等默认 agent，以及 `e2e-* / runtime-e2e-* / interrupt-*` 等测试残留。

## 后续建议

1. **清理 SQLite 残留**：3 个 SQLite 文件不参与 PostgreSQL 运行时，可直接删除（注意先备份旧数据）。
2. **清理 `pgtest_*` schema**：`DROP SCHEMA pgtest_xxx CASCADE` 即可（5 个历史调试 schema）。
3. **统一 `public` schema**：当前 Alembic 也在 `public` 下建空表，应用实际使用 `tianshu` schema，可以评估是否需要禁用 `public` 写入。
4. **种子脚本化**：将 `active-tianshu-seed.sql` 落地为 `scripts/seed_postgres.sql`，便于新环境初始化。