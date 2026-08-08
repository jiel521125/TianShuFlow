# 模型自动 Fallback 机制实现计划

## Context

当前 TianShu 配置了多个模型（MiniMax + DeepSeek），但当主模型 429 限流/配额耗尽时，系统不会自动切换到备用模型，直接报错（如 `input_polish` 返回 503，agent 主链路失败）。

用户需求："如果一个 Key 没有额度了，一定要进行降级，换另一个模型。这个要自动切换才行"。

当前代码库**没有任何 fallback 实现**（搜索 `with_fallbacks` / `FallbackChatModel` 无结果）。`LLMErrorHandlingMiddleware` 只在同一模型上重试，不切换模型。

## 核心约束

1. **`create_agent(model=...)` 要求 `BaseChatModel` 类型**：LangGraph 的 `create_agent` 会 `isinstance(model, BaseChatModel)` 检查结构化输出路径。`RunnableWithFallbacks` 无法通过此检查。→ Agent 路径必须用**中间件**实现 fallback，非 Agent 路径可以用 `with_fallbacks()`。

2. **两种调用路径**：
   - **Agent 路径**（5 个调用点）：`lead_agent/agent.py:782,863`、`client.py:350`、`subagents/executor.py:543`、`agents/factory.py` → 中间件 fallback
   - **非 Agent 路径**（4 个调用点）：`oneshot_llm.py:55`、`security_scanner.py:130`、`goal.py:258`、`memory/manager.py:675` → `with_fallbacks()`

3. **中间件顺序**：`TianShuModelFallbackMiddleware` 必须在 `LLMErrorHandlingMiddleware` **之前**（最外层），以便同模型重试先耗尽，再跨模型切换。

## 实现步骤

### 1. 提取 `_build_model_instance` 子函数

**文件**: `backend/packages/harness/tianshu/models/factory.py`

将 `create_chat_model` 主体（第 202-320 行）的单模型构建逻辑提取到 `_build_model_instance(name, *, thinking_enabled, app_config, attach_tracing, model_overrides, **kwargs) -> BaseChatModel`。`create_chat_model` 成为轻量分发器。**无行为变更**。

### 2. 添加 `ModelFallbackConfig` 配置

**文件**: `backend/packages/harness/tianshu/config/app_config.py`

新增顶层配置段（不放在 `ModelConfig` 内，避免 `extra="allow"` 转发问题）：

```python
class ModelFallbackConfig(BaseModel):
    enabled: bool = True  # 多模型时默认启用
    fallback_chain: list[str] = []  # 空=自动用 config.models[1:]
    fallback_on_quota: bool = True  # 配额耗尽时 fallback
    fallback_on_auth: bool = False  # 认证错误时 fallback（默认 False）
    fallback_on_transient: bool = True  # 5xx/超时/burst_rate 时 fallback
    propagate_to_fallback: bool = True  # 重试耗尽后 re-raise 给外层 fallback 中间件
```

在 `AppConfig` 上挂载为 `model_fallback` 字段。

### 3. 添加 fallback 异常分类谓词

**文件**: `backend/packages/harness/tianshu/agents/middlewares/llm_error_handling_middleware.py`

新增模块级函数：

```python
def _is_fallback_eligible(reason: str, *, fallback_config) -> bool:
    if reason == "quota": return fallback_config.fallback_on_quota
    if reason == "auth": return fallback_config.fallback_on_auth
    if reason in ("transient", "busy", "burst_rate"): return fallback_config.fallback_on_transient
    return False  # "circuit_open", "generic" 不 fallback
```

### 4. 修改 `LLMErrorHandlingMiddleware` 支持 re-raise

**文件**: `backend/packages/harness/tianshu/agents/middlewares/llm_error_handling_middleware.py`

- 新增 `propagate_to_fallback: bool = False` 构造参数
- 在 `wrap_model_call` / `awrap_model_call` 的重试耗尽分支（约第 832/891 行）：
  - `propagate_to_fallback=True` 且 `_is_fallback_eligible(reason)` → `raise exc`（让外层 fallback 中间件捕获）
  - 否则 → 保留旧行为（返回 `_build_user_fallback_message`）
- `propagate_to_fallback=False`（默认）→ **零行为变更**

### 5. 新建 `TianShuModelFallbackMiddleware`

**文件**: `backend/packages/harness/tianshu/agents/middlewares/model_fallback_middleware.py`（新建）

继承 LangChain 的 `ModelFallbackMiddleware`，添加异常过滤：

```python
class TianShuModelFallbackMiddleware(AgentMiddleware):
    def __init__(self, primary, fallbacks, *, app_config): ...
    
    def _should_fallback(self, exc) -> bool:
        _, reason = _classify_error(exc)
        return _is_fallback_eligible(reason, fallback_config=self._fallback_config)
    
    def wrap_model_call(self, request, handler):
        try: return handler(request)
        except Exception as exc:
            if not self._should_fallback(exc): raise
            # 遍历 fallbacks，用 request.override(model=fb) 切换模型
            # 不符合条件的错误立即中止链
            # 所有 fallback 耗尽 → re-raise 最后异常
```

`awrap_model_call` 镜像同样逻辑。复用基类的 `_sanitize_request_for_fallback` 处理 Anthropic cache_control 剥离。

### 6. 在中间件构建器中挂载

**文件**: `backend/packages/harness/tianshu/agents/middlewares/tool_error_handling_middleware.py`

在 `_build_runtime_middlewares` 中：
- 新增 `primary_model` / `fallback_models` 参数
- 在 `LLMErrorHandlingMiddleware` **之前**插入 `TianShuModelFallbackMiddleware`（仅当 `fallback_models` 非空）
- `LLMErrorHandlingMiddleware` 的 `propagate_to_fallback` 设为 `bool(fallback_models) and fallback_cfg.enabled`
- 添加排序断言：fallback 中间件 index 必须 < error 中间件 index

更新 `build_lead_runtime_middlewares` / `build_subagent_runtime_middlewares` 转发新参数。

### 7. 在 Agent 构建点构建 fallback chain

**文件改动**（5 个 Agent 构建点）：
- `backend/packages/harness/tianshu/agents/lead_agent/agent.py:782,863`
- `backend/packages/harness/tianshu/client.py:350`
- `backend/packages/harness/tianshu/subagents/executor.py:543`
- `backend/packages/harness/tianshu/agents/factory.py`

每个位置：
```python
primary_model = _build_model_instance(name=model_name, ...)
fallback_models = _build_fallback_chain(primary_name=model_name, ...)
# 传给 build_middlewares(primary_model=primary_model, fallback_models=fallback_models, ...)
# create_agent(model=primary_model) — 类型仍是 BaseChatModel
```

`_build_fallback_chain`（在 factory.py 新增）：按 `fallback_chain` 配置或 `config.models[1:]` 构建候选列表，排除主模型，防御性跳过构建失败的候选。

### 8. 非 Agent 路径用 `with_fallbacks()`

**文件**: `backend/packages/harness/tianshu/models/factory.py`

`create_chat_model` 新增 `with_fallbacks: bool = False` 参数：
- `False`（默认）→ 返回 `BaseChatModel`（旧行为，Agent 路径用）
- `True` → 返回 `RunnableWithFallbacks`，用 `_build_fallback_chain` 构建 fallback，通过谓词过滤异常

**文件改动**（4 个非 Agent 调用点，加 `with_fallbacks=True`）：
- `backend/packages/harness/tianshu/utils/oneshot_llm.py:55`
- `backend/packages/harness/tianshu/skills/security_scanner.py:130`
- `backend/packages/harness/tianshu/runtime/goal.py:258`
- `backend/packages/harness/tianshu/agents/memory/manager.py:675`

## 边界情况

| 情况 | 行为 |
|------|------|
| 仅 1 个模型 | `_build_fallback_chain` 返回 `[]`，不插入中间件，完全保留旧行为 |
| `enabled=False` | 同上 |
| fallback 模型构建失败 | 防御性跳过，主模型正常运行 |
| Auth 错误（默认 `fallback_on_auth=False`） | 不 fallback，返回用户友好消息（旧行为） |
| Quota/429 错误 | 同模型重试先耗尽，然后切换到下一个模型 |
| 所有 fallback 耗尽 | re-raise 最后异常，返回用户友好消息 |

## 验证方法

1. **单元测试**：
   - `_build_model_instance` 与旧 `create_chat_model` 行为一致
   - `create_chat_model(with_fallbacks=False)` 返回 `BaseChatModel`
   - `TianShuModelFallbackMiddleware` 在 quota 错误时切换模型
   - `LLMErrorHandlingMiddleware(propagate_to_fallback=True)` re-raise 符合条件的异常

2. **手动验证**：
   - config.yaml 配 2 个模型，主模型 key 无效，fallback key 有效
   - 发消息，观察 Gateway 日志：`Primary model failed (...)` → `Attempting fallback model: ...`
   - 响应来自 fallback 模型

3. **回归验证**：
   - 单模型配置：所有现有测试通过，无行为变更
   - `input_polish` 不再因主模型 429 直接 503（fallback 后成功）

## 关键文件清单

**核心修改**（5 个）：
- `tianshu/models/factory.py` — 提取 `_build_model_instance`，新增 `with_fallbacks` 参数和 `_build_fallback_chain`
- `tianshu/agents/middlewares/llm_error_handling_middleware.py` — `propagate_to_fallback` + `_is_fallback_eligible`
- `tianshu/agents/middlewares/model_fallback_middleware.py` — **新建** `TianShuModelFallbackMiddleware`
- `tianshu/agents/middlewares/tool_error_handling_middleware.py` — 挂载中间件 + 排序断言
- `tianshu/config/app_config.py` — `ModelFallbackConfig` schema

**辅助修改**（9 个，机械转发）：
- `tianshu/agents/lead_agent/agent.py:782,863`
- `tianshu/client.py:350`
- `tianshu/subagents/executor.py:543`
- `tianshu/utils/oneshot_llm.py:55`
- `tianshu/skills/security_scanner.py:130`
- `tianshu/runtime/goal.py:258`
- `tianshu/agents/memory/manager.py:675`

**可选**：
- `config.yaml` — 添加 `model_fallback:` 段覆盖默认值（如 `fallback_on_auth: true`）
