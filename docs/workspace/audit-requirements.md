# 工作空间（个人空间）审计要求

- 版本：v1.1
- 级别：L5
- 日期：2026-08-06

## 1. 审计范围

- 后端：迁移 0014、ORM 3 张表、WorkspaceRepository、`routers/workspaces.py`、app.py 注册
- 前端：core/workspace（types/api/hooks）、WorkspaceManager 组件、侧边栏入口、设置页签、i18n
- 文档：requirements / architecture / database / api 与实现的一致性

## 2. 功能审计清单

| 编号 | 审计项 | 通过标准 |
|------|--------|----------|
| F-1 | 空间 CRUD | GET/POST/PATCH/DELETE 全链路真实数据库读写正常 |
| F-2 | 文件夹 CRUD | 创建/重命名/删除/排序正常，级联删除生效 |
| F-3 | 文档 CRUD | 新建/详情/编辑保存/重命名/删除正常，内容持久化 |
| F-4 | 默认空间 | 首个空间自动 default；删除默认空间后自动转正 |
| F-5 | 唯一性约束 | 空间/文件夹/文档重名返回 409；大小写不敏感 |
| F-6 | 数量上限 | 空间≤50、文件夹≤500、文档≤2000 返回 413 |
| F-7 | 正文上限 | content>1MB 返回 413 |
| F-8 | 列表计数 | 空间/文件夹列表的 file_count/folder_count 准确 |
| F-9 | 前端入口 | 侧边栏入口与设置页签均可用且共用同一功能 |
| F-10 | 无 Mock | 所有验证数据来自数据库，无硬编码/伪造数据 |

## 3. 安全审计清单（TRAE-security-review 输入）

| 编号 | 安全项 | 要求 |
|------|--------|------|
| S-1 | IDOR 防护 | 空间/文件夹/文件越权访问一律 404，且不查询数据库（无存在性泄露） |
| S-2 | 用户隔离 | 仓库层所有 SQL 附加 `user_id` 条件；冗余 user_id 列双保险 |
| S-3 | 注入防护 | SQLAlchemy 参数化查询，无字符串拼接 SQL |
| S-4 | 输入校验 | 名称/内容长度、类型、数量上限服务端强制校验；未知字段不静默丢弃（400） |
| S-5 | 认证/CSRF | 路由受 AuthMiddleware 保护；写操作（POST/PATCH/DELETE）过 CSRF 防护 |
| S-6 | 内容安全 | Markdown 正文渲染复用现有 `MarkdownContent`（已含链接安全处理），不引入新的 XSS 面 |
| S-7 | 批量操作 | 删除级联在单事务内完成，失败回滚无半删状态 |
| S-8 | 敏感信息 | 响应不含用户密码/令牌等敏感字段 |

## 3.1 会话绑定与文档加载（v1.1 增量）审计清单

| 编号 | 安全项 | 要求 |
|------|--------|------|
| S-B1 | 绑定隔离 | 绑定选择器仅列出当前用户自己的空间/文件夹（复用 workspaces API 的 user_id 隔离），跨用户资源不可见 |
| S-B2 | Metadata 注入 | 绑定仅通过 `PATCH /api/threads/{id}` 写 `tianshu_workspace_*` 键，不引入新写入面；不受 `_SERVER_RESERVED_METADATA_KEYS` 冲突影响 |
| S-B3 | 文档正文注入 | 加载的文档正文以隐藏 human 消息（`hide_from_ui`）注入 `additionalInputMessages`，仅进入本会话消息流，不落任何新存储 |
| S-B4 | 内容渲染 | 隐藏消息不渲染进 UI（沿用 `isHiddenFromUIMessage` 过滤），无新 XSS 面；`<workspace_document>` 块仅作为模型输入文本 |
| S-B5 | 前端校验 | 未绑定会话不显示加载入口；加载请求仅允许绑定文件夹内文档（走文件详情 API 的 404 越权语义） |
| S-B6 | 回归 | 既有 sidecar 引用注入（conversation quotes）与新文档注入互不干扰；发送失败时 chips 不丢失 |

## 4. 验证要求

1. **后端 API 联调**：对每个端点用真实数据做 CRUD + 错误路径（400/404/409/413）冒烟；
2. **越权验证**：构造第二用户身份访问第一用户资源，确认 404；
3. **前端**：`pnpm typecheck` 零新增错误；浏览器 E2E 覆盖空间→文件夹→文档→编辑→删除全流程；
4. **回归**：设置对话框其它页签、侧边栏导航、聊天流程不受影响。

## 5. 结论判定

- 功能清单全部通过 → 功能完成；
- 安全清单全部通过 → 无可用性（exploitable）问题；
- 任一项失败 → 定位修复后回归，直至全绿。
