"""Connector error-mapping config loading (mcp/error_handlers.py).

`_load_connector_config` and `_load_generic_config` read JSON files from
`mcp/connectors/<slug>.json`; `get_user_friendly_error` falls back to the
hardcoded default mappings when no such file exists.
"""

from mcp import error_handlers
from mcp.error_handlers import (
    _load_connector_config,
    _load_generic_config,
    get_user_friendly_error,
)


def test_load_connector_config_returns_empty_list_when_file_missing():
    assert _load_connector_config("no-such-connector") == []


def test_load_connector_config_reads_error_mappings_from_json(tmp_path, monkeypatch):
    connectors_dir = tmp_path / "connectors"
    connectors_dir.mkdir()
    (connectors_dir / "widget.json").write_text(
        '{"error_mappings": [{"patterns": ["boom"], '
        '"user_message": "Widget exploded.", "http_status": "internal_error"}]}'
    )
    monkeypatch.setattr(error_handlers, "__file__", str(tmp_path / "error_handlers.py"))

    mappings = _load_connector_config("widget")

    assert mappings == [
        {
            "patterns": ["boom"],
            "user_message": "Widget exploded.",
            "http_status": "internal_error",
        }
    ]


def test_load_connector_config_returns_empty_list_on_missing_error_mappings_key(
    tmp_path, monkeypatch
):
    connectors_dir = tmp_path / "connectors"
    connectors_dir.mkdir()
    (connectors_dir / "widget.json").write_text('{"other_key": []}')
    monkeypatch.setattr(error_handlers, "__file__", str(tmp_path / "error_handlers.py"))

    assert _load_connector_config("widget") == []


def test_load_connector_config_returns_empty_list_on_malformed_json(tmp_path, monkeypatch):
    connectors_dir = tmp_path / "connectors"
    connectors_dir.mkdir()
    (connectors_dir / "widget.json").write_text("{not valid json")
    monkeypatch.setattr(error_handlers, "__file__", str(tmp_path / "error_handlers.py"))

    assert _load_connector_config("widget") == []


def test_load_generic_config_returns_empty_list_when_file_missing():
    assert _load_generic_config() == []


def test_get_user_friendly_error_falls_back_to_default_connector_mapping_without_json():
    message, status = get_user_friendly_error(
        "Bad credentials: token expired", connector_slug="github"
    )
    assert status == "unauthorized"
    assert "reconnect" in message.lower()


def test_get_user_friendly_error_prefers_json_connector_mapping_over_default(
    tmp_path, monkeypatch
):
    connectors_dir = tmp_path / "connectors"
    connectors_dir.mkdir()
    (connectors_dir / "github.json").write_text(
        '{"error_mappings": [{"patterns": ["bad credentials"], '
        '"user_message": "Custom override message.", "http_status": "unauthorized"}]}'
    )
    monkeypatch.setattr(error_handlers, "__file__", str(tmp_path / "error_handlers.py"))

    message, status = get_user_friendly_error(
        "Bad credentials: token expired", connector_slug="github"
    )

    assert message == "Custom override message."
    assert status == "unauthorized"


def test_get_user_friendly_error_falls_back_to_generic_mapping_for_unknown_connector():
    message, status = get_user_friendly_error(
        "connection refused", connector_slug="unknown-connector"
    )
    assert status == "network_error"
