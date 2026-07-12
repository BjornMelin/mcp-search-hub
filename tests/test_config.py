"""Configuration boundary tests."""

from __future__ import annotations

from decimal import Decimal

import pytest
from fastmcp.client.transports.stdio import StdioTransport
from pydantic import SecretStr, ValidationError

from mcp_search_hub.config import (
    AppSettings,
    ProviderSettings,
    resolve_env_references,
)


def test_explicit_environment_references_resolve_recursively(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SEARCH_TOKEN", "secret-value")
    value = resolve_env_references(
        {"headers": {"Authorization": "$SEARCH_TOKEN"}, "literal": "prefix-$SEARCH_TOKEN"}
    )
    assert value == {
        "headers": {"Authorization": "secret-value"},
        "literal": "prefix-$SEARCH_TOKEN",
    }
    with pytest.raises(ValueError, match="MISSING_TOKEN"):
        resolve_env_references("$MISSING_TOKEN")


def test_command_provider_builds_stdio_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SEARCH_TOKEN", "secret-value")
    provider = ProviderSettings(
        command=["python", "provider.py"],
        env={"TOKEN": "$SEARCH_TOKEN"},
        estimated_cost_usd=Decimal("0.01"),
    )
    transport = provider.resolved_transport("local")
    assert isinstance(transport, StdioTransport)
    assert transport.command == "python"
    assert transport.args == ["provider.py"]
    assert transport.env == {"TOKEN": "secret-value"}


@pytest.mark.parametrize(
    ("environment_value", "provider"),
    [
        (" ", ProviderSettings(transport="$RESOLVED_PROVIDER")),
        (" padded", ProviderSettings(transport="$RESOLVED_PROVIDER")),
        (" ", ProviderSettings(command=["$RESOLVED_PROVIDER"])),
        ("padded ", ProviderSettings(command=["$RESOLVED_PROVIDER"])),
    ],
)
def test_resolved_provider_endpoint_must_remain_trimmed_and_nonblank(
    monkeypatch: pytest.MonkeyPatch,
    environment_value: str,
    provider: ProviderSettings,
) -> None:
    monkeypatch.setenv("RESOLVED_PROVIDER", environment_value)
    with pytest.raises(ValueError, match="Resolved provider"):
        provider.resolved_transport("invalid")


@pytest.mark.parametrize(
    "provider",
    [
        {"enabled": True},
        {"transport": "https://example.test/mcp", "command": ["python"]},
        {"transport": "https://example.test/mcp", "env": {"X": "y"}},
        {"transport": ""},
        {"transport": {}},
        {"command": []},
        {"command": [" python"]},
        {"transport": "https://example.test/mcp", "weight": float("inf")},
        {"transport": "https://example.test/mcp", "tool": " "},
        {"transport": "https://example.test/mcp", "query_argument": " query"},
        {"transport": "https://example.test/mcp", "estimated_cost": "0.01"},
        {
            "transport": "https://example.test/mcp",
            "max_results_argument": "query",
        },
        {
            "transport": "https://example.test/mcp",
            "static_arguments": {"query": "fixed"},
        },
        {
            "transport": "https://example.test/mcp",
            "field_aliases": {"unknown": ["x"]},
        },
        {
            "transport": "https://example.test/mcp",
            "field_aliases": {"title": []},
        },
        {
            "transport": "https://example.test/mcp",
            "field_aliases": {"title": [" padded"]},
        },
    ],
)
def test_invalid_provider_configuration_fails_fast(provider: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ProviderSettings.model_validate(provider)


def test_disabled_provider_needs_no_transport() -> None:
    assert ProviderSettings(enabled=False).enabled is False


def test_partial_field_aliases_inherit_canonical_defaults() -> None:
    provider = ProviderSettings(
        transport="https://example.test/mcp",
        field_aliases={"title": ["heading"]},
    )
    assert provider.field_aliases["title"] == ["heading"]
    assert provider.field_aliases["raw_content"] == ["raw_content", "content"]


def test_app_settings_require_auth_for_nonlocal_http() -> None:
    with pytest.raises(ValidationError, match="network binds require"):
        AppSettings(transport="http", host="0.0.0.0")
    settings = AppSettings(
        transport="http",
        host="0.0.0.0",
        auth_tokens=[SecretStr("token")],
    )
    assert settings.host == "0.0.0.0"


def test_app_settings_validate_paths_and_provider_names() -> None:
    with pytest.raises(ValidationError, match="HTTP path"):
        AppSettings(http_path="mcp")
    with pytest.raises(ValidationError, match="reserved"):
        AppSettings(http_path="/health/")
    with pytest.raises(ValidationError, match="query, fragment"):
        AppSettings(http_path="/health?probe=1")
    with pytest.raises(ValidationError, match="percent-encoded"):
        AppSettings(http_path="/%68ealth")
    with pytest.raises(ValidationError, match="dot segments"):
        AppSettings(http_path="/health/../health")
    with pytest.raises(ValidationError, match="provider identifiers"):
        AppSettings(providers={"Bad Name": ProviderSettings(transport="https://example.test/mcp")})
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        AppSettings.model_validate({"router": {"max_provider": 1}})


@pytest.mark.parametrize("token", ["", " ", " token", "token "])
def test_app_settings_reject_blank_or_padded_auth_tokens(token: str) -> None:
    with pytest.raises(ValidationError, match="nonblank"):
        AppSettings(auth_tokens=[SecretStr(token)])


def test_app_settings_reject_duplicate_auth_tokens() -> None:
    with pytest.raises(ValidationError, match="unique"):
        AppSettings(auth_tokens=[SecretStr("token"), SecretStr("token")])
