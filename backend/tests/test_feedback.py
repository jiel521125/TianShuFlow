"""Tests for FeedbackRepository and follow-up association.

Uses the live-PostgreSQL test engine (``pg_test_engine``) for ORM tests.
"""

import pytest

from tianshu.persistence.feedback import FeedbackRepository


async def _make_feedback_repo():
    from tianshu.persistence.engine import get_session_factory

    return FeedbackRepository(get_session_factory())


# -- FeedbackRepository --


class TestFeedbackRepository:
    @pytest.mark.anyio
    async def test_create_positive(self, pg_test_engine):
        repo = await _make_feedback_repo()
        record = await repo.create(run_id="r1", thread_id="t1", rating=1)
        assert record["feedback_id"]
        assert record["rating"] == 1
        assert record["run_id"] == "r1"
        assert record["thread_id"] == "t1"
        assert "created_at" in record

    @pytest.mark.anyio
    async def test_create_negative_with_comment(self, pg_test_engine):
        repo = await _make_feedback_repo()
        record = await repo.create(
            run_id="r1",
            thread_id="t1",
            rating=-1,
            comment="Response was inaccurate",
        )
        assert record["rating"] == -1
        assert record["comment"] == "Response was inaccurate"

    @pytest.mark.anyio
    async def test_create_with_message_id(self, pg_test_engine):
        repo = await _make_feedback_repo()
        record = await repo.create(run_id="r1", thread_id="t1", rating=1, message_id="msg-42")
        assert record["message_id"] == "msg-42"

    @pytest.mark.anyio
    async def test_create_with_owner(self, pg_test_engine):
        repo = await _make_feedback_repo()
        record = await repo.create(run_id="r1", thread_id="t1", rating=1, user_id="user-1")
        assert record["user_id"] == "user-1"

    @pytest.mark.anyio
    async def test_create_invalid_rating_zero(self, pg_test_engine):
        repo = await _make_feedback_repo()
        with pytest.raises(ValueError):
            await repo.create(run_id="r1", thread_id="t1", rating=0)

    @pytest.mark.anyio
    async def test_create_invalid_rating_five(self, pg_test_engine):
        repo = await _make_feedback_repo()
        with pytest.raises(ValueError):
            await repo.create(run_id="r1", thread_id="t1", rating=5)

    @pytest.mark.anyio
    async def test_get(self, pg_test_engine):
        repo = await _make_feedback_repo()
        created = await repo.create(run_id="r1", thread_id="t1", rating=1)
        fetched = await repo.get(created["feedback_id"])
        assert fetched is not None
        assert fetched["feedback_id"] == created["feedback_id"]
        assert fetched["rating"] == 1

    @pytest.mark.anyio
    async def test_get_nonexistent(self, pg_test_engine):
        repo = await _make_feedback_repo()
        assert await repo.get("nonexistent") is None

    @pytest.mark.anyio
    async def test_list_by_run(self, pg_test_engine):
        repo = await _make_feedback_repo()
        await repo.create(run_id="r1", thread_id="t1", rating=1, user_id="user-1")
        await repo.create(run_id="r1", thread_id="t1", rating=-1, user_id="user-2")
        await repo.create(run_id="r2", thread_id="t1", rating=1, user_id="user-1")
        results = await repo.list_by_run("t1", "r1", user_id=None)
        assert len(results) == 2
        assert all(r["run_id"] == "r1" for r in results)

    @pytest.mark.anyio
    async def test_list_by_thread(self, pg_test_engine):
        repo = await _make_feedback_repo()
        await repo.create(run_id="r1", thread_id="t1", rating=1)
        await repo.create(run_id="r2", thread_id="t1", rating=-1)
        await repo.create(run_id="r3", thread_id="t2", rating=1)
        results = await repo.list_by_thread("t1")
        assert len(results) == 2
        assert all(r["thread_id"] == "t1" for r in results)

    @pytest.mark.anyio
    async def test_delete(self, pg_test_engine):
        repo = await _make_feedback_repo()
        created = await repo.create(run_id="r1", thread_id="t1", rating=1)
        deleted = await repo.delete(created["feedback_id"])
        assert deleted is True
        assert await repo.get(created["feedback_id"]) is None

    @pytest.mark.anyio
    async def test_delete_nonexistent(self, pg_test_engine):
        repo = await _make_feedback_repo()
        deleted = await repo.delete("nonexistent")
        assert deleted is False

    @pytest.mark.anyio
    async def test_aggregate_by_run(self, pg_test_engine):
        repo = await _make_feedback_repo()
        await repo.create(run_id="r1", thread_id="t1", rating=1, user_id="user-1")
        await repo.create(run_id="r1", thread_id="t1", rating=1, user_id="user-2")
        await repo.create(run_id="r1", thread_id="t1", rating=-1, user_id="user-3")
        stats = await repo.aggregate_by_run("t1", "r1")
        assert stats["total"] == 3
        assert stats["positive"] == 2
        assert stats["negative"] == 1
        assert stats["run_id"] == "r1"

    @pytest.mark.anyio
    async def test_aggregate_empty(self, pg_test_engine):
        repo = await _make_feedback_repo()
        stats = await repo.aggregate_by_run("t1", "r1")
        assert stats["total"] == 0
        assert stats["positive"] == 0
        assert stats["negative"] == 0

    @pytest.mark.anyio
    async def test_upsert_creates_new(self, pg_test_engine):
        repo = await _make_feedback_repo()
        record = await repo.upsert(run_id="r1", thread_id="t1", rating=1, user_id="u1")
        assert record["rating"] == 1
        assert record["feedback_id"]
        assert record["user_id"] == "u1"

    @pytest.mark.anyio
    async def test_upsert_updates_existing(self, pg_test_engine):
        repo = await _make_feedback_repo()
        first = await repo.upsert(run_id="r1", thread_id="t1", rating=1, user_id="u1")
        second = await repo.upsert(run_id="r1", thread_id="t1", rating=-1, user_id="u1", comment="changed my mind")
        assert second["feedback_id"] == first["feedback_id"]
        assert second["rating"] == -1
        assert second["comment"] == "changed my mind"

    @pytest.mark.anyio
    async def test_upsert_different_users_separate(self, pg_test_engine):
        repo = await _make_feedback_repo()
        r1 = await repo.upsert(run_id="r1", thread_id="t1", rating=1, user_id="u1")
        r2 = await repo.upsert(run_id="r1", thread_id="t1", rating=-1, user_id="u2")
        assert r1["feedback_id"] != r2["feedback_id"]
        assert r1["rating"] == 1
        assert r2["rating"] == -1

    @pytest.mark.anyio
    async def test_upsert_invalid_rating(self, pg_test_engine):
        repo = await _make_feedback_repo()
        with pytest.raises(ValueError):
            await repo.upsert(run_id="r1", thread_id="t1", rating=0, user_id="u1")

    @pytest.mark.anyio
    async def test_delete_by_run(self, pg_test_engine):
        repo = await _make_feedback_repo()
        await repo.upsert(run_id="r1", thread_id="t1", rating=1, user_id="u1")
        deleted = await repo.delete_by_run(thread_id="t1", run_id="r1", user_id="u1")
        assert deleted is True
        results = await repo.list_by_run("t1", "r1", user_id="u1")
        assert len(results) == 0

    @pytest.mark.anyio
    async def test_delete_by_run_nonexistent(self, pg_test_engine):
        repo = await _make_feedback_repo()
        deleted = await repo.delete_by_run(thread_id="t1", run_id="r1", user_id="u1")
        assert deleted is False

    @pytest.mark.anyio
    async def test_list_by_thread_grouped(self, pg_test_engine):
        repo = await _make_feedback_repo()
        await repo.upsert(run_id="r1", thread_id="t1", rating=1, user_id="u1")
        await repo.upsert(run_id="r2", thread_id="t1", rating=-1, user_id="u1")
        await repo.upsert(run_id="r3", thread_id="t2", rating=1, user_id="u1")
        grouped = await repo.list_by_thread_grouped("t1", user_id="u1")
        assert "r1" in grouped
        assert "r2" in grouped
        assert "r3" not in grouped
        assert grouped["r1"]["rating"] == 1
        assert grouped["r2"]["rating"] == -1

    @pytest.mark.anyio
    async def test_list_by_thread_grouped_empty(self, pg_test_engine):
        repo = await _make_feedback_repo()
        grouped = await repo.list_by_thread_grouped("t1", user_id="u1")
        assert grouped == {}

    @pytest.mark.anyio
    async def test_list_by_run_ids_is_thread_and_owner_scoped(self, pg_test_engine):
        repo = await _make_feedback_repo()
        await repo.upsert(run_id="r1", thread_id="t1", rating=1, user_id="u1")
        await repo.upsert(run_id="r2", thread_id="t1", rating=-1, user_id="u1")
        await repo.upsert(run_id="r3", thread_id="t1", rating=1, user_id="u1")
        await repo.upsert(run_id="r1", thread_id="t1", rating=-1, user_id="u2")
        await repo.upsert(run_id="r2", thread_id="t2", rating=1, user_id="u1")

        grouped = await repo.list_by_run_ids("t1", {"r1", "r2"}, user_id="u1")

        assert set(grouped) == {"r1", "r2"}
        assert grouped["r1"]["rating"] == 1
        assert grouped["r2"]["rating"] == -1

    @pytest.mark.anyio
    async def test_list_by_run_ids_empty_skips_query(self, pg_test_engine):
        repo = await _make_feedback_repo()

        assert await repo.list_by_run_ids("t1", set(), user_id="u1") == {}


# -- Follow-up association --


class TestFollowUpAssociation:
    @pytest.mark.anyio
    async def test_run_records_follow_up_via_memory_store(self):
        """MemoryRunStore stores follow_up_to_run_id in kwargs."""
        from tianshu.runtime.runs.store.memory import MemoryRunStore

        store = MemoryRunStore()
        await store.put("r1", thread_id="t1", status="success")
        # MemoryRunStore doesn't have follow_up_to_run_id as a top-level param,
        # but it can be passed via metadata
        await store.put("r2", thread_id="t1", metadata={"follow_up_to_run_id": "r1"})
        run = await store.get("r2")
        assert run["metadata"]["follow_up_to_run_id"] == "r1"

    @pytest.mark.anyio
    async def test_human_message_has_follow_up_metadata(self):
        """human_message event metadata includes follow_up_to_run_id."""
        from tianshu.runtime.events.store.memory import MemoryRunEventStore

        event_store = MemoryRunEventStore()
        await event_store.put(
            thread_id="t1",
            run_id="r2",
            event_type="human_message",
            category="message",
            content="Tell me more about that",
            metadata={"follow_up_to_run_id": "r1"},
        )
        messages = await event_store.list_messages("t1")
        assert messages[0]["metadata"]["follow_up_to_run_id"] == "r1"

    @pytest.mark.anyio
    async def test_follow_up_auto_detection_logic(self):
        """Simulate the auto-detection: latest successful run becomes follow_up_to."""
        from tianshu.runtime.runs.store.memory import MemoryRunStore

        store = MemoryRunStore()
        await store.put("r1", thread_id="t1", status="success")
        await store.put("r2", thread_id="t1", status="error")

        # Auto-detect: list_by_thread returns newest first
        recent = await store.list_by_thread("t1", limit=1)
        follow_up = None
        if recent and recent[0].get("status") == "success":
            follow_up = recent[0]["run_id"]
        # r2 (error) is newest, so no follow_up detected
        assert follow_up is None

        # Now add a successful run
        await store.put("r3", thread_id="t1", status="success")
        recent = await store.list_by_thread("t1", limit=1)
        follow_up = None
        if recent and recent[0].get("status") == "success":
            follow_up = recent[0]["run_id"]
        assert follow_up == "r3"
