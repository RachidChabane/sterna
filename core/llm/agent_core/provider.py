"""The port through which the agent execution loop reaches a model.

Defines the boundary between the loop and any specific model SDK or
HTTP client, so the loop depends on an abstraction rather than on a
concrete provider implementation.
"""
