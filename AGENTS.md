# AGENTS.md

## 会话启动

会话开始前，读取 `.trae/memory/logs.md` 中最近 5 轮会话的蒸馏内容。

## 会话流程

1. **意图识别**：分析用户意图
2. **子 Agent 调度**：根据意图调用对应子 Agent 执行任务
3. **子 Agent 经验总结**：子 Agent 执行完成后，将执行经验（步骤、问题、解决方案）写入 `.trae/memory/logs.md`
4. **审计检查**：调用审计子 Agent 对任务执行结果进行审计
   - 审计通过：进入步骤 5
   - 审计发现异常/Bug：调度对应子 Agent 继续迭代，重复步骤 2-4
5. **会话总结**：会话结束前，撰写本轮会话的蒸馏总结并写入 `.trae/memory/logs.md` 注意：**logs.md** 创建副本(**文件名：`logs_{时间}.md`)，备份原始内容。 

## 新需求开发规范

新需求开发前必须输出以下文档，作为执行基线和审计标准，统一存放在 `docs/` 目录下：

| 文档 | 颗粒度 | 图表要求 |
|------|--------|----------|
| 需求文档 | L5 | 必须包含业务流程图（Mermaid） |
| 系统架构文档 | L4 | 必须包含系统架构图（Mermaid） |
| 数据库文档 | L4 | 必须包含 ER 图（Mermaid） |
| 接口文档 | L4 | 必须包含接口调用时序图（Mermaid） |
| 审计要求文档 | L5 | - |

**图表规范**：所有图类型文档统一使用 **Mermaid** 构建。

### 开发强制约束

1. **框架执行**：开发框架确定后，必须严格按框架执行。禁止绕开框架、降级、简化、排除框架约定的任何内容。
2. **数据规范**：禁止使用 mock 数据。所有开发和测试必须使用数据库种子数据（Seed Data）。


## 模型API配置

### MINIMAX 模型配置
- Model: `MiniMax-M3` / `MiniMax-M2.7`
- APIKEY: `sk-cp-csgV97AwvphP9tOxG6mBIjbrxnUDJSmcruTTlOsQ2DuecXXXXXXpOHhFy_WP9fLmFV1fB36c66zVH9il4vzn5V6x_EZb48LM8IhTgB-JKADM`
- URL: `https://api.minimax.cn/v1/` / `https://api.minimaxi.com/anthropic`

### DEEPSEEK 模型配置
- Model: `deepseek-v4-flash` / `deepseek-v4-pro`
- APIKEY: `sk-9280980841cb4xxxxxxx1ecf`
- URL: `https://api.deepseek.com/v1/` / `https://api.deepseeki.com/anthropic`
