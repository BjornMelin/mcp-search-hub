"""Tests for the error handling utilities."""

import http

from mcp_search_hub.utils.errors import (
    AuthenticationError,
    AuthorizationError,
    CircuitBreakerOpenError,
    ConfigurationError,
    InvalidConfigurationError,
    MissingConfigurationError,
    NetworkConnectionError,
    NetworkError,
    NetworkTimeoutError,
    NoProvidersAvailableError,
    ProviderAuthenticationError,
    ProviderError,
    ProviderInitializationError,
    ProviderNotEnabledError,
    ProviderNotFoundError,
    ProviderQuotaExceededError,
    ProviderRateLimitError,
    ProviderServiceError,
    ProviderTimeoutError,
    QueryBudgetExceededError,
    QueryError,
    QueryTooComplexError,
    QueryValidationError,
    RouterError,
    RoutingStrategyError,
    SearchError,
    format_exception,
    http_error_response,
)


class TestSearchError:
    """Tests for the base SearchError class."""

    def test_init(self):
        """Test that a SearchError can be initialized with all parameters."""
        error = SearchError(
            message="Test error",
            provider="test_provider",
            status_code=418,
            original_error=ValueError("Original error"),
            details={"key": "value"},
        )

        assert error.message == "Test error"
        assert error.provider == "test_provider"
        assert error.status_code == 418
        assert isinstance(error.original_error, ValueError)
        assert error.details == {"key": "value"}
        assert str(error) == "Test error"

    def test_from_exception(self):
        """Test that from_exception creates a SearchError from another exception."""
        original = ValueError("Original error")
        error = SearchError.from_exception(
            original, message="Custom message", provider="test_provider"
        )

        assert error.message == "Custom message"
        assert error.original_error is original
        assert error.provider == "test_provider"

        # Test with default message
        error = SearchError.from_exception(original, provider="test_provider")
        assert error.message == "Original error"

    def test_to_dict(self):
        """Test that to_dict returns a dictionary representation of the error."""
        error = SearchError(
            message="Test error",
            provider="test_provider",
            details={"key": "value"},
        )

        expected = {
            "error_type": "SearchError",
            "message": "Test error",
            "provider": "test_provider",
            "details": {"key": "value"},
        }

        assert error.to_dict() == expected

        # Test without provider and details
        error = SearchError(message="Test error")
        assert error.to_dict() == {
            "error_type": "SearchError",
            "message": "Test error",
        }


class TestProviderErrors:
    """Tests for provider-related error classes."""

    def test_provider_error(self):
        """Test the ProviderError class."""
        error = ProviderError("Provider failed", "test_provider")
        assert error.message == "Provider failed"
        assert error.provider == "test_provider"
        assert error.status_code == http.HTTPStatus.BAD_GATEWAY

    def test_provider_not_found_error(self):
        """Test the ProviderNotFoundError class."""
        error = ProviderNotFoundError("nonexistent_provider")
        assert error.message == "Provider 'nonexistent_provider' not found"
        assert error.provider == "nonexistent_provider"
        assert error.status_code == http.HTTPStatus.NOT_FOUND

        # Test with custom message
        error = ProviderNotFoundError(
            "nonexistent_provider", message="Custom not found message"
        )
        assert error.message == "Custom not found message"

    def test_provider_not_enabled_error(self):
        """Test the ProviderNotEnabledError class."""
        error = ProviderNotEnabledError("disabled_provider")
        assert error.message == "Provider 'disabled_provider' is not enabled"
        assert error.provider == "disabled_provider"
        assert error.status_code == http.HTTPStatus.SERVICE_UNAVAILABLE

    def test_provider_initialization_error(self):
        """Test the ProviderInitializationError class."""
        error = ProviderInitializationError("failing_provider")
        assert error.message == "Failed to initialize provider 'failing_provider'"
        assert error.provider == "failing_provider"
        assert error.status_code == http.HTTPStatus.INTERNAL_SERVER_ERROR

    def test_provider_timeout_error(self):
        """Test the ProviderTimeoutError class."""
        # Basic initialization
        error = ProviderTimeoutError("slow_provider")
        assert error.message == "Operation timed out for provider 'slow_provider'"
        assert error.provider == "slow_provider"
        assert error.status_code == http.HTTPStatus.GATEWAY_TIMEOUT
        assert "operation" not in error.details
        assert "timeout_seconds" not in error.details

        # With operation and timeout
        error = ProviderTimeoutError("slow_provider", operation="search", timeout=10.5)
        assert (
            error.message
            == "Search operation timed out for provider 'slow_provider' after 10.5 seconds"
        )
        assert error.details["operation"] == "search"
        assert error.details["timeout_seconds"] == 10.5

        # With custom message
        error = ProviderTimeoutError("slow_provider", message="Custom timeout message")
        assert error.message == "Custom timeout message"

    def test_provider_rate_limit_error(self):
        """Test the ProviderRateLimitError class."""
        # Basic initialization
        error = ProviderRateLimitError("busy_provider")
        assert error.message == "Rate limit exceeded for provider 'busy_provider'"
        assert error.provider == "busy_provider"
        assert error.status_code == http.HTTPStatus.TOO_MANY_REQUESTS
        assert "limit_type" not in error.details
        assert "retry_after_seconds" not in error.details

        # With limit type and retry after
        error = ProviderRateLimitError(
            "busy_provider", limit_type="hourly", retry_after=60
        )
        assert (
            error.message
            == "Hourly rate limit exceeded for provider 'busy_provider', retry after 60 seconds"
        )
        assert error.details["limit_type"] == "hourly"
        assert error.details["retry_after_seconds"] == 60

    def test_provider_authentication_error(self):
        """Test the ProviderAuthenticationError class."""
        error = ProviderAuthenticationError("auth_provider")
        assert error.message == "Authentication failed for provider 'auth_provider'"
        assert error.provider == "auth_provider"
        assert error.status_code == http.HTTPStatus.UNAUTHORIZED

    def test_provider_quota_exceeded_error(self):
        """Test the ProviderQuotaExceededError class."""
        # Basic initialization
        error = ProviderQuotaExceededError("quota_provider")
        assert error.message == "Quota exceeded for provider 'quota_provider'"
        assert error.provider == "quota_provider"
        assert error.status_code == http.HTTPStatus.PAYMENT_REQUIRED
        assert "quota_type" not in error.details

        # With quota type
        error = ProviderQuotaExceededError("quota_provider", quota_type="daily")
        assert error.message == "Daily quota exceeded for provider 'quota_provider'"
        assert error.details["quota_type"] == "daily"

    def test_provider_service_error(self):
        """Test the ProviderServiceError class."""
        error = ProviderServiceError("service_provider")
        assert error.message == "Service error occurred for provider 'service_provider'"
        assert error.provider == "service_provider"
        assert error.status_code == http.HTTPStatus.BAD_GATEWAY


class TestQueryErrors:
    """Tests for query-related error classes."""

    def test_query_error(self):
        """Test the QueryError class."""
        error = QueryError("Invalid query", query="test query")
        assert error.message == "Invalid query"
        assert error.details["query"] == "test query"
        assert error.status_code == http.HTTPStatus.BAD_REQUEST

    def test_query_validation_error(self):
        """Test the QueryValidationError class."""
        validation_errors = ["Field 'x' is required", "Field 'y' must be a number"]
        error = QueryValidationError(
            "Validation failed",
            query="test query",
            validation_errors=validation_errors,
        )
        assert error.message == "Validation failed"
        assert error.details["query"] == "test query"
        assert error.details["validation_errors"] == validation_errors

    def test_query_too_complex_error(self):
        """Test the QueryTooComplexError class."""
        # Default message
        error = QueryTooComplexError(query="complex query")
        assert error.message == "Query is too complex to process"
        assert error.details["query"] == "complex query"

        # With complexity factors
        complexity_factors = {"length": 500, "special_operators": 10}
        error = QueryTooComplexError(
            query="complex query", complexity_factors=complexity_factors
        )
        assert error.details["complexity_factors"] == complexity_factors

    def test_query_budget_exceeded_error(self):
        """Test the QueryBudgetExceededError class."""
        # Default message
        error = QueryBudgetExceededError(query="expensive query")
        assert error.message == "Query would exceed allocated budget"
        assert error.details["query"] == "expensive query"
        assert error.status_code == http.HTTPStatus.PAYMENT_REQUIRED

        # With budget and cost
        error = QueryBudgetExceededError(
            query="expensive query", budget=1.0, estimated_cost=1.5
        )
        assert error.message == "Query would cost 1.5 but budget is 1.0"
        assert error.details["budget"] == 1.0
        assert error.details["estimated_cost"] == 1.5


class TestRouterErrors:
    """Tests for router-related error classes."""

    def test_router_error(self):
        """Test the RouterError class."""
        error = RouterError("Routing failed")
        assert error.message == "Routing failed"
        assert error.status_code == http.HTTPStatus.INTERNAL_SERVER_ERROR

    def test_no_providers_available_error(self):
        """Test the NoProvidersAvailableError class."""
        error = NoProvidersAvailableError(query="test query")
        assert error.message == "No search providers are available to handle the query"
        assert error.details["query"] == "test query"
        assert error.status_code == http.HTTPStatus.SERVICE_UNAVAILABLE

    def test_circuit_breaker_open_error(self):
        """Test the CircuitBreakerOpenError class."""
        # Basic initialization
        error = CircuitBreakerOpenError("failing_provider")
        assert (
            error.message == "Circuit breaker is open for provider 'failing_provider'"
        )
        assert error.details["provider"] == "failing_provider"
        assert error.status_code == http.HTTPStatus.SERVICE_UNAVAILABLE
        assert "retry_after_seconds" not in error.details

        # With retry after
        error = CircuitBreakerOpenError("failing_provider", retry_after=30)
        assert (
            error.message
            == "Circuit breaker is open for provider 'failing_provider', retry after 30 seconds"
        )
        assert error.details["retry_after_seconds"] == 30

    def test_routing_strategy_error(self):
        """Test the RoutingStrategyError class."""
        error = RoutingStrategyError("cascade")
        assert error.message == "Routing strategy 'cascade' failed"
        assert error.details["strategy"] == "cascade"


class TestConfigurationErrors:
    """Tests for configuration-related error classes."""

    def test_configuration_error(self):
        """Test the ConfigurationError class."""
        error = ConfigurationError("Config error", config_key="test_config")
        assert error.message == "Config error"
        assert error.details["config_key"] == "test_config"
        assert error.status_code == http.HTTPStatus.INTERNAL_SERVER_ERROR

    def test_missing_configuration_error(self):
        """Test the MissingConfigurationError class."""
        error = MissingConfigurationError("api_key")
        assert error.message == "Required configuration 'api_key' is missing"
        assert error.details["config_key"] == "api_key"

    def test_invalid_configuration_error(self):
        """Test the InvalidConfigurationError class."""
        error = InvalidConfigurationError("timeout", "not_a_number")
        assert (
            error.message == "Configuration 'timeout' has invalid value: not_a_number"
        )
        assert error.details["config_key"] == "timeout"
        assert error.details["value"] == "not_a_number"


class TestAuthErrors:
    """Tests for authentication and authorization error classes."""

    def test_authentication_error(self):
        """Test the AuthenticationError class."""
        error = AuthenticationError()
        assert error.message == "Authentication failed"
        assert error.status_code == http.HTTPStatus.UNAUTHORIZED

        # With custom message
        error = AuthenticationError("Invalid API key")
        assert error.message == "Invalid API key"

    def test_authorization_error(self):
        """Test the AuthorizationError class."""
        # Default message
        error = AuthorizationError()
        assert error.message == "Not authorized to perform this action"
        assert error.status_code == http.HTTPStatus.FORBIDDEN

        # With required permission
        error = AuthorizationError(required_permission="search:write")
        assert error.message == "Missing required permission: search:write"
        assert error.details["required_permission"] == "search:write"


class TestNetworkErrors:
    """Tests for network-related error classes."""

    def test_network_error(self):
        """Test the NetworkError class."""
        error = NetworkError("Network failed", url="https://example.com")
        assert error.message == "Network failed"
        assert error.details["url"] == "https://example.com"
        assert error.status_code == http.HTTPStatus.BAD_GATEWAY

    def test_network_connection_error(self):
        """Test the NetworkConnectionError class."""
        # Default message
        error = NetworkConnectionError()
        assert error.message == "Failed to establish connection"
        assert error.status_code == http.HTTPStatus.BAD_GATEWAY

        # With URL
        error = NetworkConnectionError(url="https://example.com")
        assert error.message == "Failed to establish connection to https://example.com"
        assert error.details["url"] == "https://example.com"

    def test_network_timeout_error(self):
        """Test the NetworkTimeoutError class."""
        # Default message
        error = NetworkTimeoutError()
        assert error.message == "Network operation timed out"
        assert error.status_code == http.HTTPStatus.GATEWAY_TIMEOUT

        # With URL and timeout
        error = NetworkTimeoutError(url="https://example.com", timeout=30)
        assert (
            error.message == "Request to https://example.com timed out after 30 seconds"
        )
        assert error.details["url"] == "https://example.com"
        assert error.details["timeout_seconds"] == 30


class TestUtilityFunctions:
    """Tests for utility functions."""

    def test_format_exception_with_search_error(self):
        """Test format_exception with a SearchError."""
        error = SearchError("Test error", provider="test_provider")
        formatted = format_exception(error)

        assert formatted["error_type"] == "SearchError"
        assert formatted["message"] == "Test error"
        assert formatted["provider"] == "test_provider"
        assert "traceback" in formatted

    def test_format_exception_with_standard_exception(self):
        """Test format_exception with a standard Exception."""
        error = ValueError("Test error")
        formatted = format_exception(error)

        assert formatted["error_type"] == "ValueError"
        assert formatted["message"] == "Test error"
        assert "traceback" in formatted

    def test_http_error_response_with_search_error(self):
        """Test http_error_response with a SearchError."""
        error = ProviderTimeoutError(
            "slow_provider", status_code=http.HTTPStatus.GATEWAY_TIMEOUT
        )
        response = http_error_response(error)

        assert response["error_type"] == "ProviderTimeoutError"
        assert response["message"] == "Operation timed out for provider 'slow_provider'"
        assert response["provider"] == "slow_provider"
        assert response["status_code"] == http.HTTPStatus.GATEWAY_TIMEOUT

    def test_http_error_response_with_standard_exception(self):
        """Test http_error_response with a standard Exception."""
        error = ValueError("Test error")
        response = http_error_response(error, status_code=http.HTTPStatus.BAD_REQUEST)

        assert response["error_type"] == "ValueError"
        assert response["message"] == "Test error"
        assert response["status_code"] == http.HTTPStatus.BAD_REQUEST

    def test_http_error_response_with_string(self):
        """Test http_error_response with a string."""
        response = http_error_response("Test error")

        assert response["error_type"] == "Error"
        assert response["message"] == "Test error"
        assert response["status_code"] == http.HTTPStatus.INTERNAL_SERVER_ERROR

    def test_http_error_response_with_additional_fields(self):
        """Test http_error_response with additional fields."""
        error = ValueError("Test error")
        response = http_error_response(error, request_id="123", correlation_id="abc")

        assert response["error_type"] == "ValueError"
        assert response["message"] == "Test error"
        assert response["request_id"] == "123"
        assert response["correlation_id"] == "abc"


class TestErrorHierarchy:
    """Tests for the error class hierarchy."""

    def test_inheritance_relationships(self):
        """Test that error classes have the expected inheritance relationships."""
        # Base classes
        assert issubclass(ProviderError, SearchError)
        assert issubclass(QueryError, SearchError)
        assert issubclass(RouterError, SearchError)
        assert issubclass(ConfigurationError, SearchError)
        assert issubclass(AuthenticationError, SearchError)
        assert issubclass(AuthorizationError, SearchError)
        assert issubclass(NetworkError, SearchError)

        # Provider errors
        assert issubclass(ProviderNotFoundError, ProviderError)
        assert issubclass(ProviderNotEnabledError, ProviderError)
        assert issubclass(ProviderInitializationError, ProviderError)
        assert issubclass(ProviderTimeoutError, ProviderError)
        assert issubclass(ProviderRateLimitError, ProviderError)
        assert issubclass(ProviderAuthenticationError, ProviderError)
        assert issubclass(ProviderQuotaExceededError, ProviderError)
        assert issubclass(ProviderServiceError, ProviderError)

        # Query errors
        assert issubclass(QueryValidationError, QueryError)
        assert issubclass(QueryTooComplexError, QueryError)
        assert issubclass(QueryBudgetExceededError, QueryError)

        # Router errors
        assert issubclass(NoProvidersAvailableError, RouterError)
        assert issubclass(CircuitBreakerOpenError, RouterError)
        assert issubclass(RoutingStrategyError, RouterError)

        # Configuration errors
        assert issubclass(MissingConfigurationError, ConfigurationError)
        assert issubclass(InvalidConfigurationError, ConfigurationError)

        # Network errors
        assert issubclass(NetworkConnectionError, NetworkError)
        assert issubclass(NetworkTimeoutError, NetworkError)

    def test_exception_catching(self):
        """Test that exceptions can be caught by their parent classes."""
        # ProviderTimeoutError should be caught as a ProviderError
        try:
            raise ProviderTimeoutError("test_provider")
        except ProviderError as e:
            assert e.provider == "test_provider"

        # All custom errors should be caught as SearchError
        try:
            raise QueryValidationError("Validation failed")
        except SearchError as e:
            assert e.message == "Validation failed"

        # All custom errors should be caught as Exception
        try:
            raise RouterError("Routing failed")
        except Exception as e:
            assert str(e) == "Routing failed"
