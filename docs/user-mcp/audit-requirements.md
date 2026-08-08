# 用户级 MCP 服务器注册（User MCP Registry）审计要求文档

> 粒度：L5 ｜ 版本：1.0 ｜ 日期：2026-08-07

## 1. 审计范围

本审计覆盖「用户级 MCP 服务器注册」的完整链路：数据库隔离、API 边界、运行时工具来源、缓存失效、"继承全局"语义、前端展示与安全性。

## 2. 审计项

### 2.1 数据隔离（最高优先级）

- [ ] `user_mcp` 仓储全部方法（list/get/create/update/delete）均带 `user_id` 过滤，不存在跨用户读取路径。
- [ ] 路由层使用 `get_effective_user_id()` 取值，且不信任客户端传入的任何 user_id。
- [ ] 多用户并发注册同名服务器互不影响（唯一约束为 `(user_id, name)` 复合键）。
- [ ] 代码走查：不存在把 `settings.tools.enabled_servers` 或 MCP 工具集合与系统全局配置混用的路径。

### 2.2 运行时来源

- [ ] `_make_lead_agent` 在存在 `user_mcp_tools` 时**整体替换** MCP 工具来源（先剔除 `is_mcp_tool(t)` 的全局工具，再并入用户工具）。
- [ ] 用户未注册任何服务器 → 该用户会话中无任何 MCP 工具（不得回退到系统全局配置）。
- [ ] 系统全局 `extensions_config.json` 的服务器不进入任何用户会话（管理员会话同样只用自己的注册集）。
- [ ] 非 MCP 工具（内置/技能/授权工具）不受影响，保留原行为。

### 2.3 "继承全局"语义

- [ ] `inherit_global: true`（或缺省）→ 该用户自己注册的**全部**服务器工具可用。
- [ ] `inherit_global: false` → 仅 `enabled_servers` 名单内的服务器工具可用；空名单 = 全部禁用。
- [ ] 与系统全局配置无任何关联（代码走查确认过滤对象为用户自己的工具集）。

### 2.4 缓存

- [ ] 用户 CRUD（增/改/删）自己的服务器后，该用户级 MCP 工具缓存被失效。
- [ ] 失效不波及他人缓存（key 为 `user_id`）。
- [ ] 缓存构建失败时降级行为明确（记录日志，不抛出到请求链路，不泄漏其他用户数据）。

### 2.5 API 与安全

- [ ] 状态变更请求携带 `X-CSRF-Token`（前端走 `fetcher.ts` 包装）。
- [ ] 校验完整：name 正则、transport 枚举、stdio 必填 command / sse-http 必填 url、args/env 结构；非法输入 400 不落库。
- [ ] `env` 敏感值脱敏返回（不返回明文密钥），明文仅存库。
- [ ] 404/409 语义正确（不存在 vs 重名）。

### 2.6 前端

- [ ] `MCPToolsMenu` 数据源为用户级接口，普通用户不再触发 `/api/mcp/config` 403。
- [ ] 菜单与设置页列表均只显示当前用户自己的服务器。
- [ ] 设置页 CRUD 表单三种传输类型（stdio/sse/http）均可真实注册并保存。

## 3. 验收测试（真实数据，禁 Mock）

- [ ] 后端单测：`user_mcp` 仓储 CRUD + user_id 隔离；路由 400/404/409；`resolve_user_mcp_servers`/`build_user_mcp_tools`/缓存失效。
- [ ] 集成验证（HTTP）：用户 A 注册服务器 → `GET /api/user/mcp` 仅含 A 的；用户 B 相同请求不含 A 的任何服务器。
- [ ] 会话级验证：A 发送消息，其 agent 工具列表含 A 的 MCP 服务器（按 `tianshu_mcp_server` 标签断言），不含 B 的；B 反之。
- [ ] `inherit_global` 三态验证（true / false+子集 / false+空）在会话工具集合上的实际差异。
- [ ] 前端 typecheck + prettier 全绿；修改后无 eslint 新增错误（基线错误除外）。
- [ ] 回归：既有非 MCP 功能（内置工具、技能、工作流、上传）不受影响。

## 4. 审计方法

1. 静态走查：`user_mcp` 仓储/路由/`mcp_filter.py`/`_make_lead_agent`/`services.py` 注入点。
2. 单测执行：新增与既有测试文件全量通过。
3. HTTP/浏览器实测：两个真实用户账号交叉验证隔离性。
4. 审计子 Agent 复核：对上述审计项逐条出具结论，发现异常回退迭代。
