"""The LangGraph state machine that drives one agent turn.

Wires the provider port and the tool registry into a graph of nodes
and edges that decides, at each step, whether to call the model,
run a tool, or end the turn — and streams the events defined in
`events.py` as it goes.
"""
