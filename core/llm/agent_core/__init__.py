"""Framework-free agent execution core.

Everything under this package reaches the outside world only through
plain Python types (dataclasses, enums, protocols): no Django, DRF, or
Channels import belongs anywhere in this tree, directly or by way of a
sibling module in the package. `core/llm/tests/test_agent_core_purity.py`
enforces that boundary by walking every module's import statements.
"""
