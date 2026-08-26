"""Golden transcripts for a chat turn that delegates to the coding agent.

Two locks per scenario, because the coding-agent contract has two ends.
The `.sse` transcript is every byte the browser receives for the turn.
The `.json` transcript is every request the turn sent the sandbox
orchestrator, in order, with the body each carried -- the wire the
harness inside the sandbox is driven over.

`plan_implementation` and `implement_plan` run for real: the model is a
scripted provider, the orchestrator is `orchestrator_double`, and
everything between them -- the tool handler, `CodingAgentService`, the
plan records written to the database -- is the code under test.

Unlike the other golden scenarios, this one supplies UUIDs of its own:
a conversation, a chat and a plan are database rows whose primary keys
are UUIDs, so the `uuid` normalization rule covers both the ids the
fixture supplies and the ids the code generates, numbered together by
first appearance.
"""

import json
from unittest.mock import patch

import httpx
import pytest
from django.test import SimpleTestCase
from rest_framework.test import APIClient, APITestCase

from llm.agent_core.events import Usage
from llm.agent_core.provider import (
    ProviderContentDeltaChunk,
    ProviderDoneChunk,
    ProviderGenerationIdChunk,
    ProviderToolCallDeltaChunk,
    ProviderUsageChunk,
)
from llm.tests.agent_core_doubles import ScriptedProvider
from llm.tests.conftest import make_billing_user, seed_billing_plan
from llm.tests.golden.harness import (
    FOLLOW_UP_GENERATION_ID,
    GENERATION_ID,
    MODEL_ID,
    assert_matches_golden,
    assert_matches_golden_json,
    assert_stream_is_substantive,
    capture_sse,
    seed_model_catalog,
)
from llm.tests.golden.orchestrator_double import (
    OrchestratorDouble,
    execute_response,
    progress_response,
)

pytestmark = pytest.mark.golden

STREAM_URL = "/api/llm/completions/stream-complete-v2/"

STOP = "stop"
TOOL_CALLS = "tool_calls"
FIRST_CALL_INDEX = 0

CODING_AGENT_PLAN_NAME = "coding-agent-golden-plan"
CODE_SESSION_WEEKLY_LIMIT = 100

CONVERSATION_UUID = "aaaaaaaa-0000-4000-8000-00000000c0de"
CHAT_UUID = "bbbbbbbb-0000-4000-8000-00000000c0de"

PLAN_TOOL_NAME = "plan_implementation"
IMPLEMENT_TOOL_NAME = "implement_plan"
PLAN_TOOL_CALL_ID = "toolcall-plan-implementation"
IMPLEMENT_TOOL_CALL_ID = "toolcall-implement-plan"

PLAN_JOB_ID = "job-golden-plan"
IMPLEMENT_JOB_ID = "job-golden-implement"
QUOTA_EXCEEDED_JOB_ID = "job-golden-quota-exceeded"
QUOTA_EXCEEDED_PARTIAL_COST = 18.75

TASK = "Archive expired sessions instead of deleting them"

PLAN_MARKDOWN = (
    "# Implementation Plan: Archive expired sessions\n"
    "\n"
    "## Summary\n"
    "Expired sessions are deleted outright. Archive them to a retention "
    "table first.\n"
    "\n"
    "### Step 1: Add the archive model\n"
    "**Files:** src/auth/archive.py\n"
    "Define ArchivedSession mirroring the Session columns plus archived_at.\n"
    "\n"
    "### Step 2: Archive before purging\n"
    "**Files:** src/auth/session.py\n"
    "Copy each expiring row into ArchivedSession, then delete it.\n"
)

IMPLEMENT_SUMMARY = (
    "Archived expired sessions before purging them. Added ArchivedSession, "
    "routed purge_expired through archive_then_delete, and covered it with "
    "a test."
)

QUESTION = "Should an archived session row be deleted from the live table?"
QUESTION_OPTIONS = [
    {"label": "Delete", "description": "Remove the row once it is archived."},
    {"label": "Keep", "description": "Leave the row in place and mark it archived."},
]
ANSWER = "Delete"

PLAN_STEPS = [
    {"type": "system", "tool": None, "content": "System: init", "input": None, "output": None},
    {
        "type": "tool_call",
        "tool": "Glob",
        "content": "Using Glob",
        "input": {"pattern": "src/auth/**/*.py"},
        "output": None,
    },
    {
        "type": "text",
        "tool": None,
        "content": "I'll read the session module before writing the plan.",
        "input": None,
        "output": None,
    },
    {"type": "result", "tool": None, "content": PLAN_MARKDOWN, "input": None, "output": None},
]

IMPLEMENT_STEPS = [
    {"type": "system", "tool": None, "content": "System: init", "input": None, "output": None},
    {
        "type": "tool_call",
        "tool": "mcp__ask-user__ask_user",
        "content": "Using mcp__ask-user__ask_user",
        "input": {"question": QUESTION, "options": QUESTION_OPTIONS},
        "output": None,
    },
    {
        "type": "tool_result",
        "tool": None,
        "content": ANSWER,
        "input": None,
        "output": ANSWER,
    },
    {
        "type": "tool_call",
        "tool": "Write",
        "content": "Using Write",
        "input": {"file_path": "src/auth/archive.py"},
        "output": None,
    },
    {"type": "result", "tool": None, "content": IMPLEMENT_SUMMARY, "input": None, "output": None},
]

FILES_CREATED = ["src/auth/archive.py", "tests/test_archive.py"]
FILES_MODIFIED = ["src/auth/session.py"]


def _plan_execute_response():
    """What `/coding-agent/execute` serves for a finished planning run.

    The plan text arrives as `summary`: the runner puts it in a
    `plan_content` key the endpoint's response model does not carry, and
    the chat side falls back to the summary.
    """
    return execute_response(
        success=True,
        job_id=PLAN_JOB_ID,
        summary=PLAN_MARKDOWN,
        steps=PLAN_STEPS,
        duration_ms=41000,
    )


def _implement_execute_response():
    return execute_response(
        success=True,
        job_id=IMPLEMENT_JOB_ID,
        summary=IMPLEMENT_SUMMARY,
        files_modified=FILES_MODIFIED,
        files_created=FILES_CREATED,
        steps=IMPLEMENT_STEPS,
        duration_ms=214000,
    )


def _blocked_progress_response():
    """A run stopped on the question the sandbox relayed through MCP."""
    return progress_response(
        found=True,
        step_count=2,
        total_steps=2,
        steps=IMPLEMENT_STEPS[:2],
        files_read=["src/auth/session.py"],
        total_cost_usd=0.0912,
        total_tokens=21300,
        pending_question={"question": QUESTION, "options": QUESTION_OPTIONS},
    )


def _plan_orchestrator():
    return OrchestratorDouble(execute=_plan_execute_response())


def _implement_orchestrator():
    return OrchestratorDouble(
        execute=_implement_execute_response(),
        progress=_blocked_progress_response(),
    )


def _quota_exceeded_execute_response():
    """What `/coding-agent/execute` serves for a run the runner stopped
    partway through because the user's quota ran out."""
    return execute_response(
        success=False,
        job_id=QUOTA_EXCEEDED_JOB_ID,
        error="Coding agent stopped: usage quota exceeded mid-run",
        steps=IMPLEMENT_STEPS[:2],
        total_cost_usd=QUOTA_EXCEEDED_PARTIAL_COST,
        total_tokens=64000,
        quota_exceeded=True,
        duration_ms=53000,
    )


def _quota_exceeded_orchestrator():
    return OrchestratorDouble(execute=_quota_exceeded_execute_response())


def generation_id_chunk(generation_id):
    return ProviderGenerationIdChunk(generation_id=generation_id)


def content_chunk(text):
    return ProviderContentDeltaChunk(content=text)


def usage_chunk(prompt_tokens, completion_tokens):
    return ProviderUsageChunk(
        usage=Usage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        )
    )


def tool_call_chunk(call_id, name, arguments):
    return ProviderToolCallDeltaChunk(
        index=FIRST_CALL_INDEX,
        id=call_id,
        name=name,
        arguments_delta=json.dumps(arguments),
    )


class CodingAgentGoldenTests(APITestCase):
    """Byte-exact transcripts of a chat turn that runs the coding agent."""

    def setUp(self):
        from conversations.models import Chat, Conversation

        seed_model_catalog()
        plan = seed_billing_plan(
            CODING_AGENT_PLAN_NAME,
            extra_features={"code_sessions": True},
            code_session_weekly_limit=CODE_SESSION_WEEKLY_LIMIT,
        )
        self.user = make_billing_user("coding-agent-golden@example.com", plan)
        self.conversation = Conversation.objects.create(
            id=CONVERSATION_UUID, user=self.user, name="Coding agent golden"
        )
        self.chat = Chat.objects.create(
            id=CHAT_UUID, conversation=self.conversation, model_id=MODEL_ID
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def _seed_ready_plan(self):
        from code_sessions.services.plan_service import create_plan_from_content

        return create_plan_from_content(
            plan_content=PLAN_MARKDOWN,
            conversation=self.conversation,
            task_description=TASK,
            chat=self.chat,
        )

    def _post(self, script, orchestrator):
        payload = {
            "model": MODEL_ID,
            "messages": [{"role": "user", "content": TASK}],
            "temperature": 0.2,
            "max_tokens": 256,
            "conversation_id": str(self.conversation.id),
            "chat_id": str(self.chat.id),
            "enable_file_tools": True,
        }

        provider = ScriptedProvider(script)
        patches = [
            patch("llm.views.streaming.RateLimiter", NoWaitRateLimiter),
            patch(
                "llm.views.streaming.get_user_instructions",
                return_value={"enabled": False, "content": ""},
            ),
            patch(
                "llm.services.api_key_resolver.resolve_endpoint",
                return_value=("sk-golden-fixture", None, "platform", None),
            ),
            patch(
                "llm.agent_service.dependencies.OpenRouterProvider",
                return_value=provider,
            ),
            patch.object(httpx.AsyncClient, "post", orchestrator.post),
        ]
        started = []
        try:
            for active in patches:
                active.start()
                started.append(active)
            response = self.client.post(STREAM_URL, payload, format="json")
            return capture_sse(response)
        finally:
            for active in reversed(started):
                active.stop()

    def _script(self, call_id, tool_name, arguments, closing_text):
        return [
            [
                generation_id_chunk(GENERATION_ID),
                content_chunk("Handing this to the coding agent."),
                tool_call_chunk(call_id, tool_name, arguments),
                usage_chunk(120, 40),
                ProviderDoneChunk(finish_reason=TOOL_CALLS),
            ],
            [
                generation_id_chunk(FOLLOW_UP_GENERATION_ID),
                content_chunk(closing_text),
                usage_chunk(200, 25),
                ProviderDoneChunk(finish_reason=STOP),
            ],
        ]

    # --- (a) plan mode: the turn ends with a plan waiting for review ---

    def test_plan_mode_transcript(self):
        orchestrator = _plan_orchestrator()

        raw = self._post(
            self._script(
                PLAN_TOOL_CALL_ID,
                PLAN_TOOL_NAME,
                {"task": TASK},
                "The plan is ready for your review.",
            ),
            orchestrator,
        )

        assert_stream_is_substantive(
            self,
            raw,
            ["generation_id", "content", "file_tool_executing", "file_tool_executed", "done"],
        )
        assert_matches_golden(self, "v2_coding_agent_plan_mode", raw)
        assert_matches_golden_json(
            self, "v2_coding_agent_plan_mode_orchestrator", orchestrator.request_log()
        )

    def test_plan_mode_writes_a_reviewable_plan(self):
        """The plan the turn produced is a record the user can act on."""
        from code_sessions.models import AgentPlan

        orchestrator = _plan_orchestrator()
        self._post(
            self._script(
                PLAN_TOOL_CALL_ID,
                PLAN_TOOL_NAME,
                {"task": TASK},
                "The plan is ready for your review.",
            ),
            orchestrator,
        )

        plan = AgentPlan.objects.get(conversation=self.conversation)
        self.assertEqual(plan.status, AgentPlan.Status.READY)
        self.assertEqual(plan.total_steps, 2)
        self.assertEqual(plan.plan_content, PLAN_MARKDOWN)

    # --- (b) implement mode: file changes and a completed plan ---------

    def test_implement_mode_transcript(self):
        plan = self._seed_ready_plan()
        orchestrator = _implement_orchestrator()

        raw = self._post(
            self._script(
                IMPLEMENT_TOOL_CALL_ID,
                IMPLEMENT_TOOL_NAME,
                {"plan_id": str(plan.id)},
                "The plan is implemented on its branch.",
            ),
            orchestrator,
        )

        assert_stream_is_substantive(
            self,
            raw,
            ["generation_id", "content", "file_tool_executing", "file_tool_executed", "done"],
        )
        assert_matches_golden(self, "v2_coding_agent_implement_mode", raw)
        assert_matches_golden_json(
            self, "v2_coding_agent_implement_mode_orchestrator", orchestrator.request_log()
        )

    def test_implement_mode_completes_the_plan(self):
        from code_sessions.models import AgentPlan

        plan = self._seed_ready_plan()
        orchestrator = _implement_orchestrator()

        self._post(
            self._script(
                IMPLEMENT_TOOL_CALL_ID,
                IMPLEMENT_TOOL_NAME,
                {"plan_id": str(plan.id)},
                "The plan is implemented on its branch.",
            ),
            orchestrator,
        )

        plan.refresh_from_db()
        self.assertEqual(plan.status, AgentPlan.Status.COMPLETED)
        self.assertEqual(plan.implementation_branch, f"implement/{plan.slug}")

    # --- (c) mid-run quota exhaustion: the runner stops the job early ---

    def test_implement_mode_quota_exceeded_transcript(self):
        plan = self._seed_ready_plan()
        orchestrator = _quota_exceeded_orchestrator()

        raw = self._post(
            self._script(
                IMPLEMENT_TOOL_CALL_ID,
                IMPLEMENT_TOOL_NAME,
                {"plan_id": str(plan.id)},
                "The coding agent ran out of usage quota partway through.",
            ),
            orchestrator,
        )

        assert_stream_is_substantive(
            self,
            raw,
            ["generation_id", "content", "file_tool_executing", "file_tool_executed", "done"],
        )
        assert_matches_golden(self, "v2_coding_agent_quota_exceeded", raw)
        assert_matches_golden_json(
            self, "v2_coding_agent_quota_exceeded_orchestrator", orchestrator.request_log()
        )

    def test_implement_mode_quota_exceeded_bills_the_partial_cost(self):
        from decimal import Decimal

        from code_sessions.models import AgentPlan
        from usage_quota.models import ServiceType, UsageLog

        plan = self._seed_ready_plan()
        orchestrator = _quota_exceeded_orchestrator()

        self._post(
            self._script(
                IMPLEMENT_TOOL_CALL_ID,
                IMPLEMENT_TOOL_NAME,
                {"plan_id": str(plan.id)},
                "The coding agent ran out of usage quota partway through.",
            ),
            orchestrator,
        )

        plan.refresh_from_db()
        self.assertEqual(plan.status, AgentPlan.Status.FAILED)

        log = UsageLog.objects.get(user=self.user, service=ServiceType.CODE_SESSION)
        self.assertEqual(log.request_id, QUOTA_EXCEEDED_JOB_ID)
        self.assertEqual(log.cost_usd, Decimal(str(QUOTA_EXCEEDED_PARTIAL_COST)))
        self.assertEqual(log.model_id, MODEL_ID)


class CodingAgentQuestionRoundTripGoldenTests(SimpleTestCase):
    """The question round trip, at the boundary that carries it.

    A run blocked on `ask_user` surfaces through
    `/coding-agent/progress`, and the user's reply goes back through
    `/coding-agent/answer`. Both are `CodingAgentService` calls, so the
    exchange is pinned here rather than in a chat transcript.
    """

    def setUp(self):
        self.orchestrator = OrchestratorDouble(progress=_blocked_progress_response())

    def _round_trip(self):
        from asgiref.sync import async_to_sync

        from llm.services.coding_agent_service import get_coding_agent_service

        service = get_coding_agent_service()

        async def run():
            progress = await service.get_progress(
                user_id="user-golden",
                chat_id="chat-golden",
                job_id=None,
                auth_token="token-golden",
            )
            answered = await service.send_answer(
                user_id="user-golden",
                chat_id="chat-golden",
                answer=progress["pending_question"]["options"][0]["label"],
                auth_token="token-golden",
            )
            return progress, answered

        with patch.object(httpx.AsyncClient, "post", self.orchestrator.post):
            return async_to_sync(run)()

    def test_question_round_trip_transcript(self):
        progress, answered = self._round_trip()

        self.assertEqual(progress["pending_question"]["question"], QUESTION)
        self.assertTrue(answered["success"])
        assert_matches_golden_json(
            self,
            "coding_agent_question_round_trip_orchestrator",
            {
                "requests": self.orchestrator.request_log(),
                "progress": progress,
                "answer_result": answered,
            },
        )


class NoWaitRateLimiter:
    """Rate limiter stand-in: the real one sleeps against a shared cache."""

    def wait_if_needed(self, *_args, **_kwargs):
        return None
