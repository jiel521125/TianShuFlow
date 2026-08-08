"""Discord connection routing tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.channels.discord import DiscordChannel
from app.channels.message_bus import InboundMessage, MessageBus


@pytest.fixture
async def repo(pg_test_engine):
    from tianshu.persistence.channel_connections import ChannelConnectionRepository, ChannelCredentialCipher
    from tianshu.persistence.engine import get_session_factory

    yield ChannelConnectionRepository(
        get_session_factory(),
        cipher=ChannelCredentialCipher.from_key("discord-secret"),
    )


@pytest.mark.anyio
async def test_discord_inbound_attaches_owner_identity_from_user_level_connection(repo):
    connection = await repo.upsert_connection(
        owner_user_id="alice",
        provider="discord",
        external_account_id="987",
        external_account_name="Alice",
        status="connected",
    )
    channel = DiscordChannel(
        bus=MessageBus(),
        config={"bot_token": "discord-bot", "connection_repo": repo},
    )
    inbound = InboundMessage(
        channel_name="discord",
        chat_id="C123",
        user_id="987",
        text="hello",
    )

    attached = await channel._attach_connection_identity(inbound, guild_id="G123")

    assert attached.connection_id == connection["id"]
    assert attached.owner_user_id == "alice"
    assert attached.workspace_id is None


@pytest.mark.anyio
async def test_discord_connect_command_binds_gateway_identity(repo):
    state = "discord-bind-code"
    await repo.create_oauth_state(
        owner_user_id="tianshu-user-1",
        provider="discord",
        state=state,
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    channel = DiscordChannel(
        bus=MessageBus(),
        config={"bot_token": "discord-bot", "connection_repo": repo},
    )
    message = MagicMock()
    message.author.id = 987
    message.author.display_name = "Alice"
    message.guild.id = 123
    message.guild.name = "Deer Guild"
    message.channel.id = 456
    message.channel.send = AsyncMock()

    handled = await channel._bind_connection_from_connect_code(message, state)

    connections = await repo.list_connections("tianshu-user-1")
    assert handled is True
    assert len(connections) == 1
    assert connections[0]["provider"] == "discord"
    assert connections[0]["external_account_id"] == "987"
    assert connections[0]["external_account_name"] == "Alice"
    assert connections[0]["workspace_id"] == "123"
    assert connections[0]["workspace_name"] == "Deer Guild"
    assert connections[0]["metadata"]["channel_id"] == "456"
    message.channel.send.assert_awaited_once()
