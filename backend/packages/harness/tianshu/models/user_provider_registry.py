"""Maps the user-facing ``provider`` column to a langchain chat-model class.

User-registered models in ``user_models`` carry a short string
provider identifier (``openai``, ``anthropic``, ``google``, ``deepseek``,
``custom_openai``) which is mapped here to the langchain class path
that :func:`tianshu.models.factory.create_chat_model` resolves via
``tianshu.reflection.resolve_class``. The class path must point at a
``BaseChatModel`` subclass.

This keeps ``user_models.provider`` decoupled from any internal
class-path alias. If the langchain team renames a class, we update one
entry here instead of touching every user record.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class UserProviderSpec:
    """How a user-registered ``provider`` string becomes a chat-model.

    Attributes:
        class_path: Dotted path to a ``BaseChatModel`` subclass. Resolved via
            :func:`tianshu.reflection.resolve_class` at factory time so the
            import is deferred to first use.
        default_base_url: If non-None, the value used as ``base_url`` when the
            user did not supply one. ``None`` means "use the langchain default
            endpoint" (which is what OpenAI/Anthropic users typically want).
        requires_base_url: Whether the provider *needs* an explicit
            ``base_url`` (e.g. self-hosted vLLM). The factory raises a
            helpful error when the user did not supply one.
        forward_api_key_as: The kwarg name used to pass the API key. Defaults
            to ``"api_key"`` (and the langchain alias ``openai_api_key``),
            but Google/Anthropic use different names.
    """

    class_path: str
    default_base_url: str | None = None
    requires_base_url: bool = False
    api_key_kwarg: str = "api_key"


# Source of truth for user-model provider identifiers. Adding a new
# provider here automatically exposes it in the settings UI dropdown.
USER_PROVIDERS: dict[str, UserProviderSpec] = {
    # OpenAI + OpenAI-compatible. base_url is optional because the
    # default is platform.openai.com. Most third-party providers
    # (Azure, vLLM, Together, OpenRouter, ...) supply their own.
    "openai": UserProviderSpec(
        class_path="langchain_openai.ChatOpenAI",
    ),
    "custom_openai": UserProviderSpec(
        class_path="langchain_openai.ChatOpenAI",
        requires_base_url=True,
    ),
    # Anthropic: ``base_url`` is supported by ``ChatAnthropic`` but the
    # default is api.anthropic.com. We do not require it.
    "anthropic": UserProviderSpec(
        class_path="langchain_anthropic.ChatAnthropic",
        api_key_kwarg="anthropic_api_key",
    ),
    # Google generative AI (Gemini). ``api_key`` is forwarded as
    # ``google_api_key`` to avoid colliding with OpenAI keys.
    "google": UserProviderSpec(
        class_path="langchain_google_genai.ChatGoogleGenerativeAI",
        api_key_kwarg="google_api_key",
    ),
    # DeepSeek via langchain-deepseek (the langchain_openai.ChatOpenAI
    # subclass shipped by the deepseek team).
    "deepseek": UserProviderSpec(
        class_path="langchain_deepseek.ChatDeepSeek",
    ),
    # MiniMax, StepFun, MiMo and similar small in-house providers all
    # subclass ``BaseChatOpenAI`` and live under ``tianshu.models``.
    "MiniMax": UserProviderSpec(
        class_path="tianshu.models.patched_minimax.PatchedChatMiniMax",
    ),
    "stepfun": UserProviderSpec(
        class_path="tianshu.models.patched_stepfun.PatchedChatStepFun",
    ),
    "mimo": UserProviderSpec(
        class_path="tianshu.models.patched_mimo.PatchedChatMiMo",
    ),
}


def get_provider_spec(provider: str) -> UserProviderSpec:
    """Return the spec for ``provider`` or raise ``KeyError``."""
    try:
        return USER_PROVIDERS[provider]
    except KeyError as exc:
        valid = ", ".join(sorted(USER_PROVIDERS))
        raise KeyError(
            f"Unknown model provider {provider!r}; valid providers: {valid}"
        ) from exc


def list_provider_ids() -> list[str]:
    """Return all registered provider identifiers, sorted for stable UI."""
    return sorted(USER_PROVIDERS)