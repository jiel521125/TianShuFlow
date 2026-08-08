from typing import Any

from langchain.tools import ToolRuntime

from tianshu.agents.thread_state import ThreadState

# Concrete runtime type used by all TianShu tools.
# Using dict[str, Any] for the context parameter instead of the unbound ContextT
# TypeVar prevents PydanticSerializationUnexpectedValue warnings when LangChain
# calls model_dump() on a tool's auto-generated args_schema.
Runtime = ToolRuntime[dict[str, Any], ThreadState]
