"""Tests for the Consigliere API: session lifecycle and auth boundaries.

Covers create -> generate_analysis -> continue -> clear_messages, plus
cross-user access denial and unauthenticated rejection. All LLM calls
are mocked at the service boundary (``AIAnalyzer`` / ``ConsiglierChatHandler``)
so these are integration tests of the view/serializer/model wiring, not
of the LLM itself.

Note on session "expiry": ``ConsiglierSession`` has no TTL/expiry field
or mechanism anywhere in the app — only the ``is_active`` boolean, which
``continue_session`` flips back on. There is nothing to test for actual
time-based expiration; ``test_continue_session_reactivates_and_updates_chat_group``
covers the only "reactivate a stale session" behavior that exists.
"""

import json
from unittest.mock import MagicMock, patch

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from consigliere.models import ConsiglierSession, ConsigliereMessage
from consigliere.tests.conftest import make_chat_group, valid_ai_analysis_payload

pytestmark = pytest.mark.django_db


def _create_session(client, chat_group, current_model):
    return client.post(
        reverse("consigliere:consigliere-analyze"),
        data={"chat_group": chat_group, "current_model": current_model},
        format="json",
    )


# ---------------------------------------------------------------------------
# Session lifecycle: create (analyze) -> generate_analysis -> continue
# ---------------------------------------------------------------------------


def test_analyze_creates_session_with_basic_metrics(api_client, auth_as, verified_user, haiku_model):
    client = auth_as(api_client, verified_user)
    chat_group = make_chat_group(model_id=haiku_model.model_id)

    response = _create_session(client, chat_group, haiku_model.model_id)

    assert response.status_code == 201, response.data
    session_id = response.data["session_id"]
    assert ConsiglierSession.objects.filter(id=session_id, user=verified_user).exists()
    analysis = response.data["analysis"]
    assert analysis["total_messages"] == 2
    # AI-populated fields are still empty at this point.
    assert analysis["conversation_type"] == ""
    assert analysis["insights"] == []


def test_analyze_requires_chat_group_and_current_model(api_client, auth_as, verified_user):
    client = auth_as(api_client, verified_user)

    response = client.post(
        reverse("consigliere:consigliere-analyze"), data={}, format="json"
    )

    assert response.status_code == 400


@pytest.mark.xfail(
    strict=True,
    reason=(
        "views.generate_analysis reads ai_result['recommendations'] (views.py "
        "~line 198), but AIAnalyzer.analyze_with_ai / _parse_ai_response only "
        "ever produces 'alternative_models' (see the streaming path and "
        "valid_ai_analysis_payload). The non-streaming endpoint 500s on every "
        "real AI response. Pre-existing bug, out of scope for this test task — "
        "flip to a plain pass once views.py is fixed to read 'alternative_models'."
    ),
)
def test_generate_analysis_populates_ai_fields_and_recommendations(
    api_client, auth_as, verified_user, haiku_model
):
    client = auth_as(api_client, verified_user)
    chat_group = make_chat_group(model_id=haiku_model.model_id)
    create_response = _create_session(client, chat_group, haiku_model.model_id)
    session_id = create_response.data["session_id"]

    payload = valid_ai_analysis_payload(model_id=haiku_model.model_id)
    with patch("consigliere.views.AIAnalyzer") as analyzer_cls:
        analyzer_instance = MagicMock()
        analyzer_instance.analyze_with_ai.return_value = payload
        analyzer_cls.return_value = analyzer_instance

        response = client.post(
            reverse(
                "consigliere:consigliere-generate-analysis", kwargs={"pk": session_id}
            ),
            data={"current_model": haiku_model.model_id},
            format="json",
        )

    assert response.status_code == 200, response.data
    analysis = response.data["analysis"]
    assert analysis["conversation_type"] == "technical_discussion"
    assert analysis["detected_needs"]["precision"] == "high"
    assert len(analysis["alternative_models"]) == 1
    assert analysis["alternative_models"][0]["model_id"] == "openai/gpt-4o"
    # NOTE: unlike the streaming endpoint, generate_analysis never assigns
    # analysis.recommended_model_from_conversation — no assertion on it here,
    # so this test's only failure mode is the 'recommendations' key mismatch
    # the xfail reason names (strict=True treats an error as a failure too,
    # so an unrelated assertion here would mask the fix silently).


def test_generate_analysis_rejects_missing_model_and_missing_session(
    api_client, auth_as, verified_user, haiku_model
):
    client = auth_as(api_client, verified_user)
    chat_group = make_chat_group(model_id=haiku_model.model_id)
    create_response = _create_session(client, chat_group, haiku_model.model_id)
    session_id = create_response.data["session_id"]

    missing_model_response = client.post(
        reverse("consigliere:consigliere-generate-analysis", kwargs={"pk": session_id}),
        data={},
        format="json",
    )
    assert missing_model_response.status_code == 400

    missing_session_response = client.post(
        reverse(
            "consigliere:consigliere-generate-analysis",
            kwargs={"pk": "11111111-1111-1111-1111-111111111111"},
        ),
        data={"current_model": haiku_model.model_id},
        format="json",
    )
    assert missing_session_response.status_code == 404


def test_generate_analysis_stream_completes_and_persists_recommendation(
    api_client, auth_as, verified_user, haiku_model
):
    """The streaming endpoint reads the real ``alternative_models`` contract
    (unlike its non-streaming sibling, see the xfail'd test above) and is the
    only path that persists ``recommended_model_from_conversation``.
    """
    client = auth_as(api_client, verified_user)
    chat_group = make_chat_group(model_id=haiku_model.model_id)
    create_response = _create_session(client, chat_group, haiku_model.model_id)
    session_id = create_response.data["session_id"]

    payload = valid_ai_analysis_payload(model_id=haiku_model.model_id)

    def fake_streaming(*args, **kwargs):
        yield {"step": "preparing_context", "status": "in_progress", "message": "...", "timestamp": 0}
        yield {"step": "preparing_context", "status": "completed", "message": "...", "timestamp": 0}
        yield {"_result": payload}

    # NOTE: the view's generator body (which calls AIAnalyzer) only starts
    # executing when the StreamingHttpResponse is iterated — Python
    # generators are lazy. ``response.streaming_content`` MUST therefore be
    # consumed while the patch is still active, or this silently falls
    # through to the real AIAnalyzer / a real network call.
    with patch("consigliere.views.AIAnalyzer") as analyzer_cls:
        analyzer_instance = MagicMock()
        analyzer_instance.analyze_with_ai_streaming.side_effect = fake_streaming
        analyzer_cls.return_value = analyzer_instance

        response = client.post(
            reverse("consigliere:consigliere-generate-analysis-stream", kwargs={"pk": session_id}),
            data={"current_model": haiku_model.model_id},
            format="json",
        )
        assert response.status_code == 200
        body = b"".join(response.streaming_content).decode()

    assert analyzer_instance.analyze_with_ai_streaming.call_count == 1
    events = [json.loads(line) for line in body.strip().split("\n") if line]

    assert any(e["event"] == "progress" for e in events)
    assert events[-1]["event"] == "complete"
    complete_analysis = events[-1]["data"]["analysis"]
    assert complete_analysis["recommended_from_conversation"]["model_id"] == haiku_model.model_id
    assert len(complete_analysis["alternative_models"]) == 1

    from consigliere.models import ConversationAnalysis, ModelRecommendation

    analysis = ConversationAnalysis.objects.get(session_id=session_id)
    assert analysis.recommended_model_from_conversation["model_id"] == haiku_model.model_id
    assert ModelRecommendation.objects.filter(analysis=analysis).count() == 1


def test_continue_session_reactivates_and_updates_chat_group(
    api_client, auth_as, verified_user, haiku_model
):
    client = auth_as(api_client, verified_user)
    chat_group = make_chat_group(model_id=haiku_model.model_id)
    create_response = _create_session(client, chat_group, haiku_model.model_id)
    session_id = create_response.data["session_id"]

    session = ConsiglierSession.objects.get(id=session_id)
    session.is_active = False
    session.save()

    updated_chat_group = make_chat_group(
        model_id=haiku_model.model_id, group_id="cg-updated"
    )
    response = client.post(
        reverse("consigliere:consigliere-continue-session", kwargs={"pk": session_id}),
        data={"chat_group": updated_chat_group},
        format="json",
    )

    assert response.status_code == 200, response.data
    session.refresh_from_db()
    assert session.is_active is True
    assert session.chat_group_data["id"] == "cg-updated"


def test_clear_messages_deletes_all_session_messages(
    api_client, auth_as, verified_user, haiku_model
):
    client = auth_as(api_client, verified_user)
    chat_group = make_chat_group(model_id=haiku_model.model_id)
    create_response = _create_session(client, chat_group, haiku_model.model_id)
    session_id = create_response.data["session_id"]
    session = ConsiglierSession.objects.get(id=session_id)
    ConsigliereMessage.objects.create(session=session, role="user", content="hi")
    ConsigliereMessage.objects.create(session=session, role="assistant", content="hello")

    response = client.post(
        reverse("consigliere:consigliere-clear-messages", kwargs={"pk": session_id})
    )

    assert response.status_code == 200
    assert response.data["deleted_count"] == 2
    assert ConsigliereMessage.objects.filter(session=session).count() == 0


def test_sessions_list_respects_twenty_item_limit_and_orders_newest_first(
    api_client, auth_as, verified_user, haiku_model
):
    client = auth_as(api_client, verified_user)
    chat_group = make_chat_group(model_id=haiku_model.model_id)
    for _ in range(22):
        _create_session(client, chat_group, haiku_model.model_id)

    response = client.get(reverse("consigliere:consigliere-sessions"))

    assert response.status_code == 200
    sessions = response.data["sessions"]
    assert len(sessions) == 20  # capped, even though 22 sessions exist
    created_at_values = [s["created_at"] for s in sessions]
    assert created_at_values == sorted(created_at_values, reverse=True)


# ---------------------------------------------------------------------------
# Chat: send message, retry last
# ---------------------------------------------------------------------------


def test_chat_persists_messages_and_returns_404_for_unknown_session(
    api_client, auth_as, verified_user, haiku_model
):
    client = auth_as(api_client, verified_user)
    chat_group = make_chat_group(model_id=haiku_model.model_id)
    create_response = _create_session(client, chat_group, haiku_model.model_id)
    session_id = create_response.data["session_id"]

    with patch("consigliere.views.ConsiglierChatHandler") as handler_cls:
        handler_instance = MagicMock()
        handler_instance.chat.return_value = {
            "content": "Use Haiku for cheap, fast responses.",
            "model_used": haiku_model.model_id,
            "tokens_used": 150,
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "cost": 0.001,
            "prompt_cost": 0.0006,
            "completion_cost": 0.0004,
            "latency": 0.5,
        }
        handler_cls.return_value = handler_instance

        response = client.post(
            reverse("consigliere:consigliere-chat"),
            data={
                "session_id": session_id,
                "message": "What model should I use?",
                "current_model": haiku_model.model_id,
            },
            format="json",
        )

    assert response.status_code == 200, response.data
    session = ConsiglierSession.objects.get(id=session_id)
    assert session.messages.count() == 2
    assert session.messages.filter(role="user", content="What model should I use?").exists()
    assistant_msg = session.messages.get(role="assistant")
    assert assistant_msg.content == "Use Haiku for cheap, fast responses."
    assert float(assistant_msg.cost) == pytest.approx(0.001)

    unknown_session_response = client.post(
        reverse("consigliere:consigliere-chat"),
        data={
            "session_id": "11111111-1111-1111-1111-111111111111",
            "message": "hi",
            "current_model": haiku_model.model_id,
        },
        format="json",
    )
    assert unknown_session_response.status_code == 404


def test_retry_last_deletes_exchange_or_400_when_none(
    api_client, auth_as, verified_user, haiku_model
):
    client = auth_as(api_client, verified_user)
    chat_group = make_chat_group(model_id=haiku_model.model_id)
    create_response = _create_session(client, chat_group, haiku_model.model_id)
    session_id = create_response.data["session_id"]

    empty_response = client.post(
        reverse("consigliere:consigliere-retry-last", kwargs={"pk": session_id})
    )
    assert empty_response.status_code == 400

    session = ConsiglierSession.objects.get(id=session_id)
    user_msg = ConsigliereMessage.objects.create(session=session, role="user", content="Q1")
    assistant_msg = ConsigliereMessage.objects.create(session=session, role="assistant", content="A1")

    response = client.post(
        reverse("consigliere:consigliere-retry-last", kwargs={"pk": session_id})
    )

    assert response.status_code == 200, response.data
    assert response.data["user_content"] == "Q1"
    assert not ConsigliereMessage.objects.filter(id=user_msg.id).exists()
    assert not ConsigliereMessage.objects.filter(id=assistant_msg.id).exists()


# ---------------------------------------------------------------------------
# Auth boundaries: cross-user access denied, unauthenticated rejected
# ---------------------------------------------------------------------------


def test_cross_user_access_denied_across_endpoints(
    api_client, auth_as, verified_user, other_verified_user, haiku_model
):
    """A session owned by ``verified_user`` must be invisible to
    ``other_verified_user`` across every endpoint that looks it up by pk —
    each view independently filters ``.get(pk=pk, user=request.user)``, so
    each is checked here rather than trusting one endpoint to represent all.
    """
    owner_client = auth_as(api_client, verified_user)
    chat_group = make_chat_group(model_id=haiku_model.model_id)
    create_response = _create_session(owner_client, chat_group, haiku_model.model_id)
    session_id = create_response.data["session_id"]

    intruder_client = auth_as(APIClient(), other_verified_user)

    session_detail_response = intruder_client.get(
        reverse("consigliere:consigliere-session", kwargs={"pk": session_id})
    )
    assert session_detail_response.status_code == 404

    generate_analysis_response = intruder_client.post(
        reverse("consigliere:consigliere-generate-analysis", kwargs={"pk": session_id}),
        data={"current_model": haiku_model.model_id},
        format="json",
    )
    assert generate_analysis_response.status_code == 404

    clear_messages_response = intruder_client.post(
        reverse("consigliere:consigliere-clear-messages", kwargs={"pk": session_id})
    )
    assert clear_messages_response.status_code == 404

    sessions_list_response = intruder_client.get(reverse("consigliere:consigliere-sessions"))
    assert sessions_list_response.status_code == 200
    assert sessions_list_response.data["sessions"] == []  # scoped to the intruder, not the owner


@pytest.mark.parametrize(
    "url_name,kwargs",
    [
        ("consigliere:consigliere-analyze", {}),
        ("consigliere:consigliere-sessions", {}),
        ("consigliere:consigliere-chat", {}),
    ],
)
def test_unauthenticated_requests_are_rejected(api_client, url_name, kwargs):
    if kwargs:
        url = reverse(url_name, kwargs=kwargs)
    else:
        url = reverse(url_name)

    response = api_client.get(url) if url_name.endswith("sessions") else api_client.post(url, data={}, format="json")

    assert response.status_code == 401
