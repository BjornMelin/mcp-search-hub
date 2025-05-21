"""Test provider error propagation."""

import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_search_hub.models.query import SearchQuery
from mcp_search_hub.providers.base_mcp import BaseMCPProvider
from mcp_search_hub.utils.errors import (
    ProviderAuthenticationError,
    ProviderInitializationError,
    ProviderQuotaExceededError,
    ProviderRateLimitError,
    ProviderServiceError,
    ProviderTimeoutError,
    QueryBudgetExceededError,
)


class MockedProvider(BaseMCPProvider):
    """Mock provider for testing error propagation."""

    def __init__(self, name="test", api_key="test_key", **kwargs):
        # Skip actual initialization
        self.name = name
        self.api_key = api_key
        self.initialized = True
        self.session = MagicMock()
        self.tool_name = "test_tool"

        # Setup async mocks using AsyncMock
        self.rate_limiter = MagicMock()
        self.rate_limiter.wait_if_limited = AsyncMock(return_value=True)
        self.rate_limiter.release = AsyncMock()
        self.rate_limiter.get_cooldown_remaining = MagicMock(return_value=5)

        self.budget_tracker = MagicMock()
        self.budget_tracker.check_budget = AsyncMock(return_value=True)
        self.budget_tracker.record_cost = AsyncMock()
        self.budget_tracker.get_remaining_budget = MagicMock(
            return_value={
                "daily_remaining": Decimal("10"),
                "monthly_remaining": Decimal("100"),
            }
        )

        # Mock the base cost property
        self.base_cost = Decimal("0.01")


@pytest.fixture
def provider():
    """Provider fixture for testing."""
    prov = MockedProvider()
    prov.session.call_tool = AsyncMock()
    prov._process_search_results = MagicMock(return_value=[])
    prov._calculate_actual_cost = MagicMock(return_value=Decimal("0.01"))
    return prov


@pytest.mark.asyncio
async def test_authentication_error():
    """Test API key authentication error propagation."""
    # We need to use patch here to bypass the BaseMCPProvider.__init__ method
    # which checks for API key
    from unittest.mock import patch

    with patch.object(BaseMCPProvider, "_configure_api_key") as mock_config:
        # Set up the mock to raise the exception we want to test
        mock_config.side_effect = ProviderAuthenticationError(
            provider="test",
            message="test API key is required",
            details={"env_var": "TEST_API_KEY"},
        )

        # Now this should raise our mocked exception
        with pytest.raises(ProviderAuthenticationError) as ex:
            _ = BaseMCPProvider(
                name="test",
                api_key=None,
                env_var_name="TEST_API_KEY",
                server_type="nodejs",
                args=["test-package"],
            )

        assert "test API key is required" in str(ex.value)
        assert ex.value.provider == "test"
        assert ex.value.status_code == 401  # Unauthorized


@pytest.mark.asyncio
async def test_rate_limit_error(provider):
    """Test rate limit error propagation."""
    # Set up the mock to indicate rate limiting
    provider.rate_limiter.wait_if_limited = AsyncMock(return_value=False)

    with pytest.raises(ProviderRateLimitError) as ex:
        await provider.search(SearchQuery(query="test"))

    # The exact message format is not critical, but it should contain rate limit information
    assert "rate limit" in str(ex.value).lower()
    assert ex.value.provider == "test"
    assert ex.value.status_code == 429  # Too Many Requests


@pytest.mark.asyncio
async def test_budget_exceeded_error(provider):
    """Test budget exceeded error propagation."""
    # Configure mocks for budget exceeded scenario
    provider.budget_tracker.check_budget = AsyncMock(return_value=False)
    provider.budget_tracker.get_remaining_budget = MagicMock(
        return_value={
            "daily_remaining": Decimal("0"),
            "monthly_remaining": Decimal("100"),
        }
    )

    with pytest.raises(ProviderQuotaExceededError) as ex:
        await provider.search(SearchQuery(query="test"))

    # The exact message format is not critical, but it should contain quota/budget information
    assert "quota" in str(ex.value).lower() or "budget" in str(ex.value).lower()
    assert ex.value.provider == "test"
    assert ex.value.details.get("quota_type") == "daily"
    assert ex.value.status_code == 402  # Payment Required


@pytest.mark.asyncio
async def test_query_budget_exceeded_error(provider):
    """Test query budget exceeded error propagation."""
    # Mock the estimate cost to be higher than the query budget
    provider.estimate_cost = MagicMock(return_value=0.2)

    with pytest.raises(QueryBudgetExceededError) as ex:
        await provider.search(SearchQuery(query="test", budget=0.1))

    # The exact message format is not critical, but it should mention budget and cost
    assert "budget" in str(ex.value).lower() and "cost" in str(ex.value).lower()
    assert "estimated_cost" in ex.value.details
    assert ex.value.details.get("provider") == "test"
    assert ex.value.status_code == 402  # Payment Required


@pytest.mark.asyncio
async def test_timeout_error(provider):
    """Test timeout error propagation."""
    # Mock asyncio.wait_for to raise a TimeoutError
    with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError):
        with pytest.raises(ProviderTimeoutError) as ex:
            await provider.search(SearchQuery(query="test"))

        assert "timed out" in str(ex.value)
        assert ex.value.provider == "test"
        assert ex.value.details.get("operation") == "search"
        assert ex.value.status_code == 504  # Gateway Timeout


@pytest.mark.asyncio
async def test_service_error(provider):
    """Test service error propagation."""
    # Mock session.call_tool to raise a general exception
    provider.session.call_tool = AsyncMock(
        side_effect=Exception("General service error")
    )

    with pytest.raises(ProviderServiceError) as ex:
        await provider.search(SearchQuery(query="test"))

    assert "General service error" in str(ex.value)
    assert ex.value.provider == "test"
    assert ex.value.status_code == 502  # Bad Gateway


@pytest.mark.asyncio
async def test_initialization_error(provider):
    """Test initialization error propagation."""
    provider.initialized = False
    provider.session = None
    provider.initialize = AsyncMock(
        side_effect=ProviderInitializationError(
            provider="test",
            message="Failed to initialize provider",
            details={"component": "installation"},
        )
    )

    # When initialization fails, we get a SearchResponse with error instead of exception
    response = await provider.search(SearchQuery(query="test"))

    assert response.error is not None
    assert "Failed to initialize provider" in response.error
    assert len(response.results) == 0


@pytest.mark.asyncio
async def test_error_serialization():
    """Test error serialization to dictionary."""
    error = ProviderTimeoutError(
        provider="test",
        operation="search",
        timeout=10,
        message="Operation timed out",
        details={"query": "test query"},
    )

    error_dict = error.to_dict()

    assert error_dict["error_type"] == "ProviderTimeoutError"
    assert error_dict["message"] == "Operation timed out"
    assert error_dict["provider"] == "test"
    assert "details" in error_dict
    assert error_dict["details"]["operation"] == "search"
    assert error_dict["details"]["query"] == "test query"
