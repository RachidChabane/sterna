"""Assembles the nodes, edges, and dependencies into a compiled graph.

Nodes are written as plain async functions taking the turn's state
plus what they need to do their work; they are bound to their
dependencies and to the stream writer here, so no node reaches for a
module-level collaborator and every one of them stays callable
directly from a test.

Compiling with a checkpointer is not optional: the approval pause is
built on LangGraph's interrupt, which can only resume from persisted
state. A caller that has no store of its own gets an in-memory one,
which is enough for a pause and resume inside a single process.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from .approval_nodes import approval_gate_node, approval_request_node
from .dependencies import GraphDependencies
from .emission import EventStream
from .finalize_node import finalize_node
from .model_node import model_node
from .routing import Node, route_after_model, route_after_tools
from .state import AgentTurnState
from .tool_node import tool_node


def _stream() -> EventStream:
    """The event channel of the turn currently running this node."""

    return EventStream(get_stream_writer())


def build_agent_graph(
    deps: GraphDependencies,
    *,
    checkpointer: Optional[BaseCheckpointSaver] = None,
) -> CompiledStateGraph:
    """Compile the agent loop that runs against `deps`."""

    async def model(state: AgentTurnState) -> Dict[str, Any]:
        return await model_node(state, deps, _stream())

    async def approval_request(state: AgentTurnState) -> Dict[str, Any]:
        return await approval_request_node(state, deps)

    def approval_gate(state: AgentTurnState) -> Dict[str, Any]:
        return approval_gate_node(state)

    async def tools(state: AgentTurnState) -> Dict[str, Any]:
        return await tool_node(state, deps, _stream())

    async def finalize(state: AgentTurnState) -> Dict[str, Any]:
        return await finalize_node(state, deps, _stream())

    def after_model(state: AgentTurnState) -> str:
        return route_after_model(state, deps)

    def after_tools(state: AgentTurnState) -> str:
        return route_after_tools(state)

    builder: StateGraph = StateGraph(AgentTurnState)
    builder.add_node(Node.MODEL, model)
    builder.add_node(Node.APPROVAL_REQUEST, approval_request)
    builder.add_node(Node.APPROVAL_GATE, approval_gate)
    builder.add_node(Node.TOOLS, tools)
    builder.add_node(Node.FINALIZE, finalize)

    builder.add_edge(START, Node.MODEL)
    builder.add_conditional_edges(
        Node.MODEL,
        after_model,
        [Node.FINALIZE, Node.APPROVAL_REQUEST, Node.TOOLS, END],
    )
    builder.add_edge(Node.APPROVAL_REQUEST, Node.APPROVAL_GATE)
    builder.add_edge(Node.APPROVAL_GATE, Node.TOOLS)
    builder.add_conditional_edges(
        Node.TOOLS, after_tools, [Node.MODEL, Node.APPROVAL_REQUEST]
    )
    builder.add_edge(Node.FINALIZE, END)

    return builder.compile(checkpointer=checkpointer or InMemorySaver())
