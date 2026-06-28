"""FeedbackEvent 记忆方法测试。"""

from __future__ import annotations

from comedy_agent.memory.models import FeedbackEventData
from comedy_agent.memory.unified import UnifiedMemory


def test_save_and_list_feedback_events():
    memory = UnifiedMemory(db_url="sqlite:///:memory:")

    saved = memory.save_feedback_event(
        FeedbackEventData(
            user_id="u1",
            session_id="s1",
            target_type="message",
            target_id="msg-1",
            rating=1,
            comment="不错",
        )
    )
    assert saved.event_id
    assert saved.user_id == "u1"

    events = memory.list_feedback_events("u1")
    assert len(events) == 1
    assert events[0].target_id == "msg-1"
    assert events[0].rating == 1


def test_feedback_event_upsert():
    memory = UnifiedMemory(db_url="sqlite:///:memory:")

    memory.save_feedback_event(
        FeedbackEventData(
            user_id="u1",
            target_type="message",
            target_id="msg-2",
            rating=1,
        )
    )
    memory.save_feedback_event(
        FeedbackEventData(
            user_id="u1",
            target_type="message",
            target_id="msg-2",
            rating=-1,
        )
    )
    events = memory.list_feedback_events("u1")
    assert len(events) == 1
    assert events[0].rating == -1


def test_mark_feedback_event_ingested():
    memory = UnifiedMemory(db_url="sqlite:///:memory:")

    saved = memory.save_feedback_event(
        FeedbackEventData(
            user_id="u1",
            target_type="artifact",
            target_id="art-1",
            rating=1,
        )
    )
    ok = memory.mark_feedback_event_ingested(saved.event_id)
    assert ok is True

    events = memory.list_feedback_events("u1", ingested=True)
    assert len(events) == 1
    assert events[0].ingested is True


def test_list_feedback_events_filter_target_type():
    memory = UnifiedMemory(db_url="sqlite:///:memory:")

    memory.save_feedback_event(
        FeedbackEventData(user_id="u1", target_type="message", target_id="m1", rating=1)
    )
    memory.save_feedback_event(
        FeedbackEventData(user_id="u1", target_type="artifact", target_id="a1", rating=-1)
    )

    messages = memory.list_feedback_events("u1", target_type="message")
    assert len(messages) == 1
    assert messages[0].target_type == "message"
