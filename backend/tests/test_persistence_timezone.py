"""Regression tests for #3120: stores must emit tz-aware ISO timestamps.

On PostgreSQL the ``DateTime(timezone=True)`` columns are natively tz-aware,
but the SQL ``_row_to_dict`` helpers still normalize through
:func:`tianshu.utils.time.coerce_iso`; this guards the API output format so
the frontend's ``new Date(...)`` never receives a timezone-less string.
"""

import re

import pytest

_TZ_SUFFIX_RE = re.compile(r"(?:\+\d{2}:\d{2}|Z)$")


def _assert_tz_aware(value: str | None, *, context: str) -> None:
    assert value, f"{context}: expected ISO string, got {value!r}"
    assert _TZ_SUFFIX_RE.search(value), f"{context}: timestamp lacks tz suffix: {value!r}"


@pytest.mark.anyio
async def test_thread_meta_emits_tz_aware_timestamps(pg_test_engine):
    from tianshu.persistence.engine import get_session_factory
    from tianshu.persistence.thread_meta import ThreadMetaRepository

    repo = ThreadMetaRepository(get_session_factory())

    created = await repo.create("t-tz", user_id="u1", display_name="tz")
    _assert_tz_aware(created["created_at"], context="thread_meta.create.created_at")
    _assert_tz_aware(created["updated_at"], context="thread_meta.create.updated_at")

    # Second read from DB exercises the same _row_to_dict path on a value
    # PostgreSQL has round-tripped.
    fetched = await repo.get("t-tz", user_id="u1")
    _assert_tz_aware(fetched["created_at"], context="thread_meta.get.created_at")
    _assert_tz_aware(fetched["updated_at"], context="thread_meta.get.updated_at")

    listed = await repo.search(user_id="u1")
    assert listed, "search must return the created row"
    _assert_tz_aware(listed[0]["created_at"], context="thread_meta.search.created_at")
    _assert_tz_aware(listed[0]["updated_at"], context="thread_meta.search.updated_at")


@pytest.mark.anyio
async def test_run_repository_emits_tz_aware_timestamps(pg_test_engine):
    from tianshu.persistence.engine import get_session_factory
    from tianshu.persistence.run import RunRepository

    repo = RunRepository(get_session_factory())

    await repo.put("r-tz", thread_id="t-tz", user_id="u1")
    row = await repo.get("r-tz", user_id="u1")
    _assert_tz_aware(row["created_at"], context="run.get.created_at")
    _assert_tz_aware(row["updated_at"], context="run.get.updated_at")


@pytest.mark.anyio
async def test_feedback_repository_emits_tz_aware_timestamps(pg_test_engine):
    from tianshu.persistence.engine import get_session_factory
    from tianshu.persistence.feedback import FeedbackRepository

    repo = FeedbackRepository(get_session_factory())

    record = await repo.create(run_id="r-tz", thread_id="t-tz", rating=1, user_id="u1")
    _assert_tz_aware(record["created_at"], context="feedback.create.created_at")


@pytest.mark.anyio
async def test_run_event_store_emits_tz_aware_timestamps(pg_test_engine):
    from tianshu.persistence.engine import get_session_factory
    from tianshu.runtime.events.store.db import DbRunEventStore

    store = DbRunEventStore(get_session_factory())

    await store.put(
        thread_id="t-tz",
        run_id="r-tz",
        event_type="log",
        category="log",
        content="hello",
    )
    events = await store.list_events("t-tz", "r-tz", user_id=None)
    assert events, "expected at least one event"
    _assert_tz_aware(events[0]["created_at"], context="run_event.list.created_at")
