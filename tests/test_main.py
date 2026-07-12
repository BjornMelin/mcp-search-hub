"""Command-line configuration precedence tests."""

from __future__ import annotations

import sys
from typing import Any

import pytest

from mcp_search_hub import main as main_module
from mcp_search_hub.config import AppSettings


def test_cli_override_precedes_invalid_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class StubServer:
        def __init__(self, settings: AppSettings) -> None:
            captured["settings"] = settings

        async def run_stdio(self) -> None:
            captured["transport"] = "stdio"

        async def run_http(self) -> None:
            raise AssertionError("HTTP transport must be overridden")

    monkeypatch.setenv("TRANSPORT", "http")
    monkeypatch.setenv("HOST", "0.0.0.0")
    monkeypatch.setenv("AUTH_TOKENS", "[]")
    monkeypatch.setattr(sys, "argv", ["mcp-search-hub", "--transport", "stdio"])
    monkeypatch.setattr(main_module, "SearchServer", StubServer)

    with pytest.raises(SystemExit) as exit_info:
        main_module.main()

    settings = captured["settings"]
    assert isinstance(settings, AppSettings)
    assert settings.transport == "stdio"
    assert settings.host == "0.0.0.0"
    assert captured["transport"] == "stdio"
    assert exit_info.value.code == 0
