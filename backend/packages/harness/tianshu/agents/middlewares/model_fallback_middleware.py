"""Model fallback middleware: switch to alternative models on eligible errors.

Sits *outside* ``LLMErrorHandlingMiddleware`` in the middleware chain so that
same-model retries exhaust first; only then does this middleware catch the
re-raised exception and try the next configured model. Non-eligible errors
(auth, generic) are re-raised immediately so the fallback chain is not wasted
on errors that won't be fixed by switching models.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import (
    ModelCallResult,
    ModelRequest,
    ModelResponse,
)
from langchain.chat_models import BaseChatModel

from tianshu.agents.middlewares.llm_error_handling_middleware import (
    _BUSY_PATTERNS,
    _BURST_PATTERNS,
    _QUOTA_PATTERNS,
    _AUTH_PATTERNS,
    _RETRIABLE_STATUS_CODES,
    _extract_error_code,
    _extract_error_detail,
    _extract_status_code,
    _is_fallback_eligible,
    _matches_any,
)
from tianshu.config.app_config import AppConfig

logger = logging.getLogger(__name__)


def _classify_error_reason(exc: BaseException) -> str:
    """Classify an exception into a reason string for fallback eligibility.

    Mirrors ``LLMErrorHandlingMiddleware._classify_error`` but as a module-level
    function so ``TianShuModelFallbackMiddleware`` can use it without an
    ``LLMErrorHandlingMiddleware`` instance. Returns only the reason (not the
    retriable bool) since fallback eligibility is decided by
    ``_is_fallback_eligible``.
    """
    detail = _extract_error_detail(exc)
    lowered = detail.lower()
    error_code = _extract_error_code(exc)
    status_code = _extract_status_code(exc)

    if _matches_any(lowered, _QUOTA_PATTERNS) or _matches_any(str(error_code).lower(), _QUOTA_PATTERNS):
        return "quota"
    if _matches_any(lowered, _AUTH_PATTERNS):
        return "auth"
    if _matches_any(lowered, _BURST_PATTERNS) or _matches_any(str(error_code).lower(), _BURST_PATTERNS):
        return "burst_rate"

    exc_name = exc.__class__.__name__
    if exc_name in {
        "APITimeoutError",
        "APIConnectionError",
        "InternalServerError",
        "ReadError",
        "RemoteProtocolError",
        "StreamChunkTimeoutError",
    }:
        return "transient"
    if isinstance(exc, IndexError):
        return "transient"
    if status_code in _RETRIABLE_STATUS_CODES:
        return "transient"
    if _matches_any(lowered, _BUSY_PATTERNS):
        return "busy"

    return "generic"


def _model_name(model: BaseChatModel) -> str:
    """Best-effort model name for logging."""
    return getattr(model, "model_name", None) or getattr(model, "model", None) or type(model).__name__


class TianShuModelFallbackMiddleware(AgentMiddleware[AgentState]):
    """Try fallback models when the primary fails with an eligible error.

    Unlike LangChain's built-in ``ModelFallbackMiddleware`` (which catches all
    exceptions), this middleware uses TianShu's error classification to filter:
    only quota/rate-limit/transient errors trigger a model switch. Auth errors
    and generic exceptions are re-raised immediately.
    """

    def __init__(
        self,
        primary: BaseChatModel | None,
        fallbacks: list[BaseChatModel],
        *,
        app_config: AppConfig,
    ) -> None:
        super().__init__()
        self._primary = primary  # May be None; not used for calls, only for logging.
        self._fallbacks = list(fallbacks)
        self._fallback_config = app_config.model_fallback

    def _should_fallback(self, exc: BaseException) -> bool:
        reason = _classify_error_reason(exc)
        return _is_fallback_eligible(reason, fallback_config=self._fallback_config)

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelCallResult:
        try:
            return handler(request)
        except Exception as exc:
            if not self._should_fallback(exc):
                raise
            logger.warning(
                "Primary model failed (%s); attempting %d fallback(s)",
                _extract_error_detail(exc),
                len(self._fallbacks),
            )
            last_exc = exc
            for fb in self._fallbacks:
                try:
                    logger.info("Attempting fallback model: %s", _model_name(fb))
                    fb_request = request.override(model=fb)
                    return handler(fb_request)
                except Exception as exc2:
                    last_exc = exc2
                    if self._should_fallback(exc2):
                        logger.warning(
                            "Fallback model %s also failed (%s); trying next",
                            _model_name(fb),
                            _extract_error_detail(exc2),
                        )
                        continue
                    raise
            raise last_exc

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelCallResult:
        try:
            return await handler(request)
        except Exception as exc:
            if not self._should_fallback(exc):
                raise
            logger.warning(
                "Primary model failed (%s); attempting %d fallback(s)",
                _extract_error_detail(exc),
                len(self._fallbacks),
            )
            last_exc = exc
            for fb in self._fallbacks:
                try:
                    logger.info("Attempting fallback model: %s", _model_name(fb))
                    fb_request = request.override(model=fb)
                    return await handler(fb_request)
                except Exception as exc2:
                    last_exc = exc2
                    if self._should_fallback(exc2):
                        logger.warning(
                            "Fallback model %s also failed (%s); trying next",
                            _model_name(fb),
                            _extract_error_detail(exc2),
                        )
                        continue
                    raise
            raise last_exc
