"""Exercise the shipped array-query example through the public search tool."""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import httpx
import pytest
from fastmcp import Client, FastMCP

from mcp_search_hub.config import AppSettings, ProviderSettings
from mcp_search_hub.models import HealthStatus, SearchQuery
from mcp_search_hub.providers import ProviderRegistry
from mcp_search_hub.server import SearchServer

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def _example_settings(monkeypatch: pytest.MonkeyPatch) -> AppSettings:
    monkeypatch.setenv("PARALLEL_SEARCH_SESSION_ID", "example-conversation-session")
    monkeypatch.setenv("PROVIDERS", (EXAMPLES / "parallel.json").read_text())
    return AppSettings(environment="test")


@pytest.mark.parametrize(
    ("excerpts", "snippet"),
    [
        ([" First excerpt. ", "", "Second excerpt."], "First excerpt.\nSecond excerpt."),
        ([], None),
        ([" ", ""], None),
        ("Plain excerpt.", "Plain excerpt."),
        ([1, "legacy value"], "[1, 'legacy value']"),
    ],
)
@pytest.mark.asyncio
async def test_array_query_example_over_http(
    monkeypatch: pytest.MonkeyPatch, excerpts: object, snippet: str | None
) -> None:
    settings = _example_settings(monkeypatch)
    downstream = FastMCP("array-query-provider")
    received: list[dict[str, Any]] = []
    requests: list[httpx.Request] = []

    def web_search(objective: str, search_queries: list[str], session_id: str) -> dict[str, object]:
        received.append(
            {"objective": objective, "search_queries": search_queries, "session_id": session_id}
        )
        return {
            "results": [
                {
                    "title": "FastMCP client configuration",
                    "url": "https://example.test/client",
                    "excerpts": excerpts,
                },
                {"title": "Another page", "url": "https://example.test/another"},
            ]
        }

    downstream.tool(web_search)
    app = downstream.http_app(stateless_http=True, json_response=True)
    original_send = httpx.AsyncClient.send
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app)) as local_client,
    ):

        async def send(
            self: httpx.AsyncClient, request: httpx.Request, *args: Any, **kwargs: Any
        ) -> httpx.Response:
            del self
            requests.append(request)
            assert str(request.url) == "https://search.parallel.ai/mcp"
            assert request.headers["User-Agent"] == "mcp-search-hub/1.0.0"
            assert "authorization" not in request.headers
            return await original_send(local_client, request, *args, **kwargs)

        monkeypatch.setattr(httpx.AsyncClient, "send", send)
        server = SearchServer(settings)
        async with Client(server.mcp) as client:
            result = await client.call_tool(
                "search",
                {
                    "query": "FastMCP HTTP client configuration",
                    "providers": ["parallel"],
                    "max_results": 1,
                    "include_raw_content": True,
                },
            )
            payload = cast(dict[str, Any], result.structured_content)
            assert [item["provider"] for item in payload["successful_providers"]] == ["parallel"]
            assert payload["failed_providers"] == []
            assert len(payload["results"]) == 1
            item = payload["results"][0]
            assert item["title"] == "FastMCP client configuration"
            assert item["url"] == "https://example.test/client"
            assert item["snippet"] == snippet
            assert item["raw_content"] is None
            assert item["sources"][0]["provider"] == "parallel"
            assert item["sources"][0]["rank"] == 1
    assert requests
    assert any(json.loads(request.content).get("method") == "initialize" for request in requests)
    assert any(json.loads(request.content).get("method") == "tools/call" for request in requests)
    assert received == [
        {
            "objective": "Find relevant web pages for the supplied search query.",
            "search_queries": ["FastMCP HTTP client configuration"],
            "session_id": "example-conversation-session",
        }
    ]


@pytest.mark.parametrize("failure", ["error", "timeout", "cancel"])
@pytest.mark.asyncio
async def test_array_query_example_failures(monkeypatch: pytest.MonkeyPatch, failure: str) -> None:
    registry = ProviderRegistry.from_settings(_example_settings(monkeypatch))
    definition = registry.definitions()[0]
    assert definition.query_as_list is True
    downstream = FastMCP("array-query-failures")
    started = asyncio.Event()
    release = asyncio.Event()

    async def web_search(
        objective: str, search_queries: list[str], session_id: str
    ) -> dict[str, object]:
        assert objective
        assert search_queries == ["failure example"]
        assert session_id == "example-conversation-session"
        started.set()
        if failure == "error":
            raise ValueError("provider failure")
        await release.wait()
        return {"results": []}

    downstream.tool(web_search)
    # Keep all resolved example fields; replace only the network with an in-memory MCP server.
    registry = ProviderRegistry([replace(definition, transport=downstream)])
    server = SearchServer(_example_settings(monkeypatch), registry=registry)
    async with Client(server.mcp) as client:
        query = SearchQuery(
            query="failure example",
            providers=["parallel"],
            timeout_seconds=0.1 if failure == "timeout" else 5,
        )
        try:
            if failure == "cancel":
                task = asyncio.create_task(server.orchestrator.execute(query))
                await asyncio.wait_for(started.wait(), timeout=5)
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
            else:
                response = await client.call_tool("search", query.model_dump(mode="json"))
                payload = cast(dict[str, Any], response.structured_content)
                assert started.is_set()
                assert payload["results"] == []
                if failure == "error":
                    assert payload["failed_providers"] == [
                        {"provider": "parallel", "error_type": "ToolError"}
                    ]
                    assert payload["timed_out_providers"] == []
                else:
                    assert payload["timed_out_providers"] == ["parallel"]
                    assert payload["failed_providers"] == []
            if failure != "error":
                assert registry.active_sessions() == []
                assert registry.health()["parallel"].status == HealthStatus.UNHEALTHY
                assert registry.health()["parallel"].message == "TimeoutError"
        finally:
            release.set()


def test_examples_preserve_empty_and_scalar_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PROVIDERS", raising=False)
    assert AppSettings().providers == {}
    settings = AppSettings(
        providers={"scalar": ProviderSettings(transport="https://example.test/mcp")},
    )
    assert ProviderRegistry.from_settings(settings).definitions()[0].query_as_list is False
