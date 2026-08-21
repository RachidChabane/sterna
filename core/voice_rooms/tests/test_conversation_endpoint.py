"""Tests for GET /api/voice-rooms/rooms/{id}/conversation/.

Covers the session-resolution fallback: an active session is preferred,
but when only an ended session exists its transcript must still render
(this was the reported bug — the endpoint used to only ever look at
active sessions and silently returned an empty conversation).
"""

from datetime import timedelta

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from authentication.models import User
from voice_rooms.models import VoiceRoom, VoiceRoomMessage, VoiceRoomSession


def conversation_url(room_id) -> str:
    return reverse("voice-room-conversation", kwargs={"pk": room_id})


@pytest.fixture
def user(db):
    return User.objects.create_user(email="voice-conv@test.com", password="x")


@pytest.fixture
def other_user(db):
    return User.objects.create_user(email="voice-conv-other@test.com", password="x")


@pytest.fixture
def client(user):
    c = APIClient()
    c.force_authenticate(user=user)
    return c


@pytest.fixture
def room(user):
    return VoiceRoom.objects.create(user=user, name="Product Roadmap Brainstorm")


def _add_messages(session, count=5):
    for i in range(count):
        VoiceRoomMessage.objects.create(
            session=session,
            role="user" if i % 2 == 0 else "assistant",
            content=f"message {i}",
        )


@pytest.mark.django_db
class TestConversationSessionResolution:
    def test_empty_room_returns_null_session_and_no_messages(self, client, room):
        resp = client.get(conversation_url(room.id))

        assert resp.status_code == 200
        assert resp.data == {"session_id": None, "messages": []}

    def test_active_session_is_preferred_over_ended_session(self, client, room):
        ended = VoiceRoomSession.objects.create(room=room, status="ended")
        _add_messages(ended, count=3)

        active = VoiceRoomSession.objects.create(room=room, status="listening")
        _add_messages(active, count=2)

        resp = client.get(conversation_url(room.id))

        assert resp.status_code == 200
        assert resp.data["session_id"] == str(active.id)
        assert len(resp.data["messages"]) == 2

    def test_falls_back_to_most_recent_ended_session_when_none_active(
        self, client, room
    ):
        """Regression test for the reported bug: an ENDED session with
        messages must still be returned when no active session exists."""
        session = VoiceRoomSession.objects.create(room=room, status="ended")
        _add_messages(session, count=5)

        resp = client.get(conversation_url(room.id))

        assert resp.status_code == 200
        assert resp.data["session_id"] == str(session.id)
        assert len(resp.data["messages"]) == 5

    def test_falls_back_to_most_recently_started_session_of_any_status(
        self, client, room
    ):
        older = VoiceRoomSession.objects.create(room=room, status="ended")
        _add_messages(older, count=1)
        VoiceRoomSession.objects.filter(pk=older.pk).update(
            started_at=older.started_at - timedelta(days=365)
        )

        newer = VoiceRoomSession.objects.create(room=room, status="ended")
        _add_messages(newer, count=4)

        resp = client.get(conversation_url(room.id))

        assert resp.status_code == 200
        assert resp.data["session_id"] == str(newer.id)
        assert len(resp.data["messages"]) == 4

    def test_explicit_session_param_selects_that_session(self, client, room):
        first = VoiceRoomSession.objects.create(room=room, status="ended")
        _add_messages(first, count=2)

        second = VoiceRoomSession.objects.create(room=room, status="listening")
        _add_messages(second, count=1)

        resp = client.get(conversation_url(room.id), {"session": str(first.id)})

        assert resp.status_code == 200
        assert resp.data["session_id"] == str(first.id)
        assert len(resp.data["messages"]) == 2

    def test_explicit_session_param_for_foreign_session_404s(
        self, client, room, other_user
    ):
        other_room = VoiceRoom.objects.create(user=other_user, name="Someone else's room")
        foreign_session = VoiceRoomSession.objects.create(room=other_room, status="ended")

        resp = client.get(
            conversation_url(room.id), {"session": str(foreign_session.id)}
        )

        assert resp.status_code == 404

    def test_explicit_session_param_with_malformed_uuid_returns_400(
        self, client, room
    ):
        resp = client.get(conversation_url(room.id), {"session": "not-a-uuid"})

        assert resp.status_code == 400

    def test_requires_authentication(self, room):
        resp = APIClient().get(conversation_url(room.id))

        assert resp.status_code == 401

    def test_cannot_fetch_conversation_for_another_users_room(
        self, client, other_user
    ):
        other_room = VoiceRoom.objects.create(user=other_user, name="Not mine")

        resp = client.get(conversation_url(other_room.id))

        assert resp.status_code == 404


def clear_conversation_url(room_id) -> str:
    return reverse("voice-room-clear-conversation", kwargs={"pk": room_id})


@pytest.mark.django_db
class TestClearConversation:
    def test_clear_ends_active_session_and_empties_conversation(self, client, room):
        session = VoiceRoomSession.objects.create(room=room, status="listening")
        _add_messages(session, count=3)

        resp = client.post(clear_conversation_url(room.id))
        assert resp.status_code == 200
        assert resp.data == {"status": "cleared"}

        session.refresh_from_db()
        assert session.status == "ended"

        follow_up = client.get(conversation_url(room.id))
        assert follow_up.data["messages"] == []

    def test_clear_on_an_already_ended_session_still_empties_conversation(
        self, client, room
    ):
        """Regression test: since `conversation` falls back to the most
        recent session of any status, clearing must delete the messages
        themselves — ending an (already-ended) session is not enough, or
        the "cleared" transcript immediately resurfaces on the next GET."""
        session = VoiceRoomSession.objects.create(room=room, status="ended")
        _add_messages(session, count=5)

        resp = client.post(clear_conversation_url(room.id))
        assert resp.status_code == 200

        follow_up = client.get(conversation_url(room.id))
        assert follow_up.data["messages"] == []

    def test_clear_does_not_delete_other_rooms_messages(
        self, client, room, user
    ):
        other_room = VoiceRoom.objects.create(user=user, name="Other room")
        other_session = VoiceRoomSession.objects.create(room=other_room, status="ended")
        _add_messages(other_session, count=2)

        session = VoiceRoomSession.objects.create(room=room, status="listening")
        _add_messages(session, count=1)

        client.post(clear_conversation_url(room.id))

        assert VoiceRoomMessage.objects.filter(session=other_session).count() == 2
