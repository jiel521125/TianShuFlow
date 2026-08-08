"""Tests for Telegram deep-link channel connections."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.channels.message_bus import MessageBus
from app.channels.telegram import TelegramChannel


@pytest.fixture
async def repo(pg_test_engine):
    from tianshu.persistence.channel_connections import ChannelConnectionRepository, ChannelCredentialCipher
    from tianshu.persistence.engine import get_session_factory

    yield ChannelConnectionRepository(
        get_session_factory(),
        cipher=ChannelCredentialCipher.from_key("telegram-secret"),
    )


def _telegram_update(*, text: str = "/start", user_id: int = 42, chat_id: int = 100, chat_type: str = "private"):
    update = MagicMock()
    update.effective_user.id = user_id
    update.effective_user.username = "alice"
    update.effective_user.full_name = "Alice Example"
    update.effective_chat.id = chat_id
    update.effective_chat.type = chat_type
    update.message.text = text
    update.message.message_id = 55
    update.message.reply_to_message = None
    update.message.reply_text = AsyncMock()
    return update


@pytest.mark.anyio
async def test_start_with_deep_link_state_binds_telegram_chat(repo):
    state = "telegram-bind-state"
    await repo.create_oauth_state(
        owner_user_id="tianshu-user-1",
        provider="telegram",
        state=state,
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    channel = TelegramChannel(
        bus=MessageBus(),
        config={"bot_token": "test-token", "connection_repo": repo},
    )
    update = _telegram_update(text=f"/start {state}")
    context = MagicMock()
    context.args = [state]

    await channel._cmd_start(update, context)

    connections = await repo.list_connections("tianshu-user-1")
    assert len(connections) == 1
    assert connections[0]["provider"] == "telegram"
    assert connections[0]["external_account_id"] == "42"
    assert connections[0]["external_account_name"] == "Alice Example"
    assert connections[0]["workspace_id"] == "100"
    assert connections[0]["metadata"]["chat_type"] == "private"
    update.message.reply_text.assert_awaited_once()
    assert "connected" in update.message.reply_text.await_args.args[0].lower()


@pytest.mark.anyio
async def test_start_token_bypasses_allowed_users_filter(repo):
    # A newly allowlisted-but-unbound user must be able to bootstrap their first
    # bind via the deep-link start token even though their Telegram id is not yet
    # in allowed_users. The allowed_users gate must run after token handling.
    state = "telegram-bind-state"
    await repo.create_oauth_state(
        owner_user_id="tianshu-user-1",
        provider="telegram",
        state=state,
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    channel = TelegramChannel(
        bus=MessageBus(),
        config={
            "bot_token": "test-token",
            "connection_repo": repo,
            "allowed_users": [999],  # newcomer (42) is not whitelisted
        },
    )
    update = _telegram_update(text=f"/start {state}", user_id=42)
    context = MagicMock()
    context.args = [state]

    await channel._cmd_start(update, context)

    connections = await repo.list_connections("tianshu-user-1")
    assert len(connections) == 1
    assert connections[0]["external_account_id"] == "42"
    assert "connected" in update.message.reply_text.await_args.args[0].lower()


@pytest.mark.anyio
async def test_bound_telegram_message_publishes_connection_identity(repo):
    connection = await repo.upsert_connection(
        owner_user_id="tianshu-user-1",
        provider="telegram",
        external_account_id="42",
        external_account_name="Alice Example",
        workspace_id="100",
        metadata={"chat_type": "private"},
    )
    bus = MessageBus()
    channel = TelegramChannel(
        bus=bus,
        config={"bot_token": "test-token", "connection_repo": repo},
    )
    channel._main_loop = __import__("asyncio").get_event_loop()
    channel._send_running_reply = AsyncMock()

    await channel._on_text(_telegram_update(text="hello"), None)
    inbound = await bus.get_inbound()

    assert inbound.connection_id == connection["id"]
    assert inbound.owner_user_id == "tianshu-user-1"
    assert inbound.workspace_id == "100"
    assert inbound.user_id == "42"
    assert inbound.chat_id == "100"
    assert inbound.text == "hello"
