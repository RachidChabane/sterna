"""A stand-in for the sandbox orchestrator at the HTTP boundary.

Every route a coding-agent chat turn can reach answers from a fixture,
and every request is recorded in the order it was sent. Replacing
`httpx.AsyncClient.post` with the double's own `post` puts the seam
exactly where the two services meet: the tool handler, the coding-agent
service and the payload each builds all run for real, and only the
network is fixed.

`REQUEST_LOG` entries carry the URL and the JSON body. Headers are left
out on purpose -- they carry a per-request id and a bearer token that no
replay reproduces.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

OK_STATUS = 200

EXECUTE_ROUTE = "/coding-agent/execute"
PROGRESS_ROUTE = "/coding-agent/progress"
ANSWER_ROUTE = "/coding-agent/answer"
BASH_ROUTE = "/fs/bash"

UNROUTED_ERROR = "No orchestrator fixture is registered for this route."

# Exactly the fields `CodingAgentExecuteResponse` serializes. A payload
# naming anything else would not survive the real endpoint's response
# model, so the builder refuses it.
EXECUTE_RESPONSE_FIELDS = (
    "success",
    "job_id",
    "summary",
    "files_modified",
    "files_created",
    "steps",
    "error",
    "duration_ms",
    "total_tokens",
    "total_cost_usd",
    "quota_exceeded",
)

# Exactly the fields `CodingAgentProgressResponse` serializes.
PROGRESS_RESPONSE_FIELDS = (
    "found",
    "step_count",
    "total_steps",
    "completed",
    "exit_code",
    "files_created",
    "files_modified",
    "files_read",
    "files_deleted",
    "steps",
    "error",
    "summary",
    "total_cost_usd",
    "total_tokens",
    "pending_question",
)

_EXECUTE_DEFAULTS: Dict[str, Any] = {
    "success": False,
    "job_id": None,
    "summary": None,
    "files_modified": [],
    "files_created": [],
    "steps": [],
    "error": None,
    "duration_ms": 0,
    "total_tokens": 0,
    "total_cost_usd": 0.0,
    "quota_exceeded": False,
}

_PROGRESS_DEFAULTS: Dict[str, Any] = {
    "found": False,
    "step_count": 0,
    "total_steps": 0,
    "completed": False,
    "exit_code": None,
    "files_created": [],
    "files_modified": [],
    "files_read": [],
    "files_deleted": [],
    "steps": [],
    "error": None,
    "summary": None,
    "total_cost_usd": 0.0,
    "total_tokens": 0,
    "pending_question": None,
}


def _build(defaults: Dict[str, Any], allowed, overrides: Dict[str, Any]) -> Dict[str, Any]:
    unknown = set(overrides) - set(allowed)
    if unknown:
        raise ValueError(f"The orchestrator does not serve these fields: {sorted(unknown)}")
    payload = dict(defaults)
    payload.update(overrides)
    return payload


def execute_response(**overrides) -> Dict[str, Any]:
    """One `/coding-agent/execute` reply, in the shape the endpoint serves."""
    return _build(_EXECUTE_DEFAULTS, EXECUTE_RESPONSE_FIELDS, overrides)


def progress_response(**overrides) -> Dict[str, Any]:
    """One `/coding-agent/progress` reply, in the shape the endpoint serves."""
    return _build(_PROGRESS_DEFAULTS, PROGRESS_RESPONSE_FIELDS, overrides)


class FixtureResponse:
    """The parts of an `httpx.Response` a caller in this path reads."""

    def __init__(self, payload: Dict[str, Any]) -> None:
        self.status_code = OK_STATUS
        self._payload = payload
        self.text = json.dumps(payload)

    def json(self) -> Dict[str, Any]:
        return self._payload


class OrchestratorDouble:
    """Answers the orchestrator's routes from fixtures and logs the traffic."""

    def __init__(
        self,
        *,
        execute: Optional[Dict[str, Any]] = None,
        progress: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._execute = execute or execute_response()
        self._progress = progress or progress_response()
        self.requests: List[Dict[str, Any]] = []

    async def post(self, url: str, *, json: Optional[Dict[str, Any]] = None, **_kwargs):
        self.requests.append({"url": url, "payload": json})
        return FixtureResponse(self._route(url))

    def _route(self, url: str) -> Dict[str, Any]:
        if url.endswith(EXECUTE_ROUTE):
            return self._execute
        if url.endswith(PROGRESS_ROUTE):
            return self._progress
        if url.endswith(ANSWER_ROUTE):
            return {"success": True}
        if url.endswith(BASH_ROUTE):
            return {"success": True, "output": ""}
        return {"success": False, "error": UNROUTED_ERROR}

    def request_log(self) -> List[Dict[str, Any]]:
        """The recorded traffic, ready to compare against a golden."""
        return self.requests
