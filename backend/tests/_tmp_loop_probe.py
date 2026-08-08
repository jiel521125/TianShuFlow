"""Throwaway probe: verify cross-event-loop engine usage with TestClient + asyncpg."""
import asyncio
import os
import uuid

import anyio


def main():
    import psycopg

    url = os.environ["TIANSHU_TEST_POSTGRES_URL"]
    schema = f"pgtest_{uuid.uuid4().hex[:12]}"
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute(f'CREATE SCHEMA "{schema}"')

    from tianshu.config.database_config import DatabaseConfig
    from tianshu.persistence.channel_connections import ChannelConnectionRepository
    from tianshu.persistence.engine import close_engine, get_session_factory, init_engine_from_config

    async def setup():
        await init_engine_from_config(
            DatabaseConfig(backend="postgres", postgres_url=url, postgres_schema=schema)
        )
        return ChannelConnectionRepository(get_session_factory())

    repo = anyio.run(setup)

    # Simulate TestClient running on a different loop
    from app.gateway.auth.models import User
    from app.gateway.routers import channel_connections
    from fastapi.testclient import TestClient
    from _router_auth_helpers import make_authed_test_app
    from uuid import UUID

    async def seed():
        await repo.upsert_connection(
            owner_user_id=str(UUID("11111111-2222-3333-4444-555555555555")),
            provider="slack",
            external_account_id="U123",
            status="connected",
        )

    anyio.run(seed)

    app = make_authed_test_app(
        user_factory=lambda: User(
            id=UUID("11111111-2222-3333-4444-555555555555"),
            email="alice@example.com",
            password_hash="x",
            system_role="admin",
        )
    )
    app.state.channel_connections_config = object()
    app.state.channel_connection_repo = repo
    app.include_router(channel_connections.router)

    with TestClient(app) as client:
        response = client.get("/api/channels/connections")
        print("status:", response.status_code)

    async def teardown():
        await close_engine()

    anyio.run(teardown)

    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
    print("OK - no cross-loop errors")


if __name__ == "__main__":
    main()
