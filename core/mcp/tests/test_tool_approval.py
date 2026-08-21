"""Tool-call approval gating: model-level approve/reject/is_valid logic,
IDOR boundaries on the approvals API, and the registry's defense-in-depth
ownership check that runs even after an approval has been granted
(mcp/models.py MCPToolApproval, mcp/views.py, mcp/registry.py).
"""

import json
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from asgiref.sync import async_to_sync
from django.urls import reverse
from django.utils import timezone

from mcp.exceptions import MCPError
from mcp.models import MCPServer, MCPToolApproval
from mcp.registry import MCPRegistry

from .conftest import make_approval, make_server, make_tool

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Model-level approve/reject/is_valid gating logic
# ---------------------------------------------------------------------------


def test_approve_sets_status_scope_and_decided_at(user_a):
    server = make_server(user_a)
    tool = make_tool(server)
    approval = make_approval(user_a, tool)

    approval.approve(scope=MCPToolApproval.ApprovalScope.PERMANENT)

    assert approval.status == MCPToolApproval.ApprovalStatus.APPROVED
    assert approval.scope == MCPToolApproval.ApprovalScope.PERMANENT
    assert approval.decided_at is not None


def test_approve_session_scope_sets_24h_expiry(user_a):
    server = make_server(user_a)
    tool = make_tool(server)
    approval = make_approval(user_a, tool)

    before = timezone.now()
    approval.approve(scope=MCPToolApproval.ApprovalScope.SESSION)
    after = timezone.now()

    assert approval.expires_at is not None
    assert before + timedelta(hours=23, minutes=59) <= approval.expires_at <= after + timedelta(hours=24, minutes=1)


def test_reject_sets_status_and_decided_at(user_a):
    server = make_server(user_a)
    tool = make_tool(server)
    approval = make_approval(user_a, tool)

    approval.reject()

    assert approval.status == MCPToolApproval.ApprovalStatus.REJECTED
    assert approval.decided_at is not None


def test_is_valid_false_when_not_approved(user_a):
    server = make_server(user_a)
    tool = make_tool(server)
    pending = make_approval(user_a, tool, status=MCPToolApproval.ApprovalStatus.PENDING)
    rejected = make_approval(user_a, tool, status=MCPToolApproval.ApprovalStatus.REJECTED)

    assert pending.is_valid() is False
    assert rejected.is_valid() is False


def test_is_valid_once_scope_true_until_executed(user_a):
    server = make_server(user_a)
    tool = make_tool(server)
    approval = make_approval(user_a, tool)
    approval.approve(scope=MCPToolApproval.ApprovalScope.ONCE)

    assert approval.is_valid() is True

    execution = approval.executions.create(
        tool=tool,
        arguments={},
        status="success",
        completed_at=timezone.now(),
    )
    assert approval.is_valid() is False
    execution.delete()


def test_is_valid_session_scope_respects_expiry(user_a):
    server = make_server(user_a)
    tool = make_tool(server)
    approval = make_approval(user_a, tool)
    approval.approve(scope=MCPToolApproval.ApprovalScope.SESSION)

    assert approval.is_valid() is True

    approval.expires_at = timezone.now() - timedelta(minutes=1)
    approval.save(update_fields=["expires_at"])
    assert approval.is_valid() is False


def test_is_valid_permanent_scope_always_true(user_a):
    server = make_server(user_a)
    tool = make_tool(server)
    approval = make_approval(user_a, tool)
    approval.approve(scope=MCPToolApproval.ApprovalScope.PERMANENT)

    # Even after "use", permanent approvals remain valid.
    approval.executions.create(
        tool=tool, arguments={}, status="success", completed_at=timezone.now()
    )
    assert approval.is_valid() is True


# ---------------------------------------------------------------------------
# API: auth required + IDOR on approvals/executions
# ---------------------------------------------------------------------------


def test_approve_endpoint_rejects_unauthenticated(api_client, user_a):
    server = make_server(user_a)
    tool = make_tool(server)
    approval = make_approval(user_a, tool)

    response = api_client.post(reverse("mcp:approval-approve", args=[approval.id]))
    assert response.status_code == 401


def test_user_cannot_approve_another_users_approval(api_client, auth_as, user_a, user_b):
    server_b = make_server(user_b)
    tool_b = make_tool(server_b)
    approval_b = make_approval(user_b, tool_b)

    client = auth_as(api_client, user_a)
    response = client.post(reverse("mcp:approval-approve", args=[approval_b.id]))

    assert response.status_code == 404
    approval_b.refresh_from_db()
    assert approval_b.status == MCPToolApproval.ApprovalStatus.PENDING


def test_user_cannot_reject_another_users_approval(api_client, auth_as, user_a, user_b):
    server_b = make_server(user_b)
    tool_b = make_tool(server_b)
    approval_b = make_approval(user_b, tool_b)

    client = auth_as(api_client, user_a)
    response = client.post(reverse("mcp:approval-reject", args=[approval_b.id]))

    assert response.status_code == 404
    approval_b.refresh_from_db()
    assert approval_b.status == MCPToolApproval.ApprovalStatus.PENDING


def test_pending_endpoint_only_lists_own_approvals(api_client, auth_as, user_a, user_b):
    server_a = make_server(user_a)
    tool_a = make_tool(server_a)
    make_approval(user_a, tool_a)

    server_b = make_server(user_b)
    tool_b = make_tool(server_b)
    make_approval(user_b, tool_b)

    client = auth_as(api_client, user_a)
    response = client.get(reverse("mcp:approval-pending"))

    assert response.status_code == 200
    assert len(response.data) == 1
    assert response.data[0]["tool"]["name"] == tool_a.name


def test_approve_already_decided_approval_returns_400(api_client, auth_as, user_a):
    server = make_server(user_a)
    tool = make_tool(server)
    approval = make_approval(user_a, tool, status=MCPToolApproval.ApprovalStatus.APPROVED)

    client = auth_as(api_client, user_a)
    response = client.post(reverse("mcp:approval-approve", args=[approval.id]))

    assert response.status_code == 400


# ---------------------------------------------------------------------------
# Approve endpoint: execution wiring (registry mocked — no real network/IO)
# ---------------------------------------------------------------------------


def test_approve_executes_tool_and_records_success(api_client, auth_as, user_a):
    server = make_server(user_a)
    tool = make_tool(server)
    approval = make_approval(user_a, tool, proposed_arguments={"query": "hello"})

    fake_registry = MagicMock()
    fake_registry.call_tool_by_name = AsyncMock(
        return_value={"content": [{"type": "text", "text": "ok"}], "is_error": False}
    )

    client = auth_as(api_client, user_a)
    with patch("mcp.views.get_registry", return_value=fake_registry):
        response = client.post(
            reverse("mcp:approval-approve", args=[approval.id]),
            data={"scope": "once"},
            format="json",
        )

    assert response.status_code == 200, response.data
    approval.refresh_from_db()
    assert approval.status == MCPToolApproval.ApprovalStatus.APPROVED
    assert response.data["execution"]["status"] == "success"

    fake_registry.call_tool_by_name.assert_awaited_once()
    _, call_kwargs = fake_registry.call_tool_by_name.call_args
    assert call_kwargs["arguments"] == {"query": "hello"}
    # Defense-in-depth: caller's user must be threaded through so the
    # registry can re-verify ownership independently of the queryset scope.
    assert call_kwargs["user"] == user_a


def test_approve_records_error_when_tool_call_fails(api_client, auth_as, user_a):
    server = make_server(user_a)
    tool = make_tool(server)
    approval = make_approval(user_a, tool)

    fake_registry = MagicMock()
    fake_registry.call_tool_by_name = AsyncMock(side_effect=MCPError("boom"))

    client = auth_as(api_client, user_a)
    with patch("mcp.views.get_registry", return_value=fake_registry):
        response = client.post(
            reverse("mcp:approval-approve", args=[approval.id]),
            data={"scope": "once"},
            format="json",
        )

    assert response.status_code >= 400
    assert response.data["execution"]["status"] == "error"
    execution_id = response.data["execution"]["id"]
    from mcp.models import MCPToolExecution

    execution = MCPToolExecution.objects.get(id=execution_id)
    assert execution.error_message == "boom"


def test_reject_marks_approval_rejected(api_client, auth_as, user_a):
    server = make_server(user_a)
    tool = make_tool(server)
    approval = make_approval(user_a, tool)

    client = auth_as(api_client, user_a)
    response = client.post(reverse("mcp:approval-reject", args=[approval.id]))

    assert response.status_code == 200
    approval.refresh_from_db()
    assert approval.status == MCPToolApproval.ApprovalStatus.REJECTED


# ---------------------------------------------------------------------------
# MCPToolViewSet.call — creates a pending approval, never auto-executes
# ---------------------------------------------------------------------------


def test_call_tool_creates_pending_approval_without_executing(api_client, auth_as, user_a):
    server = make_server(user_a)
    tool = make_tool(server)

    client = auth_as(api_client, user_a)
    response = client.post(
        reverse("mcp:tool-call", args=[tool.id]),
        data={"arguments": {"x": 1}},
        format="json",
    )

    assert response.status_code == 202
    assert response.data["status"] == "approval_required"
    approval = MCPToolApproval.objects.get(id=response.data["approval"]["id"])
    assert approval.status == MCPToolApproval.ApprovalStatus.PENDING
    assert approval.user_id == user_a.id


# ---------------------------------------------------------------------------
# Gap: approval creation accepts any tool_id, including tools that live on
# another user's server (not just preconfigured/shared ones). Downstream
# execution is still blocked by the registry ownership check, so this is
# information disclosure (tool name/description leak via the approval
# response), not cross-tenant execution. Documented, not fixed here.
# ---------------------------------------------------------------------------


def test_GAP_approval_create_accepts_other_users_tool_id(api_client, auth_as, user_a, user_b):
    """DOCUMENTS A GAP: MCPToolApprovalSerializer.tool_id uses an
    unscoped `MCPTool.objects.all()` queryset, and MCPToolApprovalViewSet
    is a full ModelViewSet with no ownership check in `create`/`perform_create`.
    A can create an approval row referencing B's private tool, learning
    its name/description/server. Execution still fails at the registry's
    ownership check (see test_registry_blocks_cross_tenant_execution),
    so this is info-disclosure, not a cross-tenant exploit — but the
    approval row itself should never have been created for A.
    """
    server_b = make_server(user_b, name="B's private server")
    tool_b = make_tool(server_b, name="b_only_tool", description="B's secret tool")

    client = auth_as(api_client, user_a)
    response = client.post(
        reverse("mcp:approval-list"),
        data={"tool_id": tool_b.id, "proposed_arguments": {}},
        format="json",
    )

    assert response.status_code == 201, (
        "If this now 4xxs, the unscoped tool_id queryset has been fixed — "
        "update/remove this gap-documenting test."
    )
    body = json.dumps(response.data)
    assert "b_only_tool" in body  # confirms the leak this test documents


# ---------------------------------------------------------------------------
# Registry-level defense-in-depth: ownership re-checked at execution time
# ---------------------------------------------------------------------------


def test_registry_blocks_cross_tenant_execution(user_a, user_b):
    """call_tool_by_name must reject execution when the caller does not
    own the server, independent of any queryset-level scoping upstream.
    No client/network mocking needed: ownership is checked before any
    connection is attempted.
    """
    server_b = make_server(user_b)
    tool_b = make_tool(server_b)

    registry = MCPRegistry()
    with pytest.raises(PermissionError):
        async_to_sync(registry.call_tool_by_name)(
            tool_name=tool_b.name,
            server_id=str(server_b.id),
            server_transport_type=server_b.transport_type,
            arguments={},
            user=user_a,
        )


def test_registry_blocks_execution_on_preconfigured_server_for_any_user(user_a):
    """Preconfigured servers have user=None. A user attempting to execute
    against one directly (server.user_id is None != user.id) must be
    rejected the same way as any other cross-tenant attempt."""
    preconfigured = MCPServer.objects.create(
        user=None,
        name="Preconfigured",
        npm_package="@preconfigured/server",
        transport_type=MCPServer.TransportType.SANDBOXED,
        is_preconfigured=True,
    )
    tool = make_tool(preconfigured)

    registry = MCPRegistry()
    with pytest.raises(PermissionError):
        async_to_sync(registry.call_tool_by_name)(
            tool_name=tool.name,
            server_id=str(preconfigured.id),
            server_transport_type=preconfigured.transport_type,
            arguments={},
            user=user_a,
        )
