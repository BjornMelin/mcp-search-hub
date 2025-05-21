"""Error handling utilities.

This module provides a comprehensive hierarchy of exception classes for the MCP Search Hub.
It defines a base SearchError class and specialized subclasses for different types of errors
that can occur in the application.
"""

import http
import traceback
from typing import Any, TypeVar

# Type variable for self-referential return types
T = TypeVar("T", bound="SearchError")


class SearchError(Exception):
    """Base class for all search-related exceptions in the application.

    All custom exceptions should inherit from this class to ensure consistent
    error handling throughout the application.
    """

    def __init__(
        self,
        message: str,
        provider: str | None = None,
        status_code: int = http.HTTPStatus.INTERNAL_SERVER_ERROR,
        original_error: Exception | None = None,
        details: dict[str, Any] | None = None,
    ):
        """Initialize the error with context information.

        Args:
            message: Human-readable error message
            provider: Name of the provider that raised the error, if applicable
            status_code: HTTP status code to use when converting to HTTP responses
            original_error: The original exception that caused this error, if any
            details: Additional structured details about the error
        """
        self.message = message
        self.provider = provider
        self.status_code = status_code
        self.original_error = original_error
        self.details = details or {}
        super().__init__(message)

    @classmethod
    def from_exception(
        cls: type[T], exc: Exception, message: str | None = None, **kwargs
    ) -> T:
        """Create an error instance from another exception.

        Args:
            exc: The exception to wrap
            message: Custom message to use (defaults to str(exc))
            **kwargs: Additional arguments to pass to the constructor

        Returns:
            A new instance of the error class
        """
        return cls(message=message or str(exc), original_error=exc, **kwargs)

    def to_dict(self) -> dict[str, Any]:
        """Convert the error to a dictionary representation.

        Returns:
            A dictionary containing error details suitable for serialization
        """
        result = {
            "error_type": self.__class__.__name__,
            "message": self.message,
        }

        if self.provider:
            result["provider"] = self.provider

        if self.details:
            result["details"] = self.details

        return result


# Provider-related errors


class ProviderError(SearchError):
    """Base class for errors related to search providers."""

    def __init__(
        self,
        message: str,
        provider: str | None = None,
        status_code: int = http.HTTPStatus.BAD_GATEWAY,
        **kwargs,
    ):
        """Initialize a provider error.

        Args:
            message: Error message
            provider: Name of the provider
            status_code: HTTP status code (defaults to 502 Bad Gateway)
            **kwargs: Additional arguments passed to SearchError
        """
        super().__init__(message, provider, status_code, **kwargs)


class ProviderNotFoundError(ProviderError):
    """Error raised when a requested provider doesn't exist."""

    def __init__(
        self,
        provider: str,
        message: str | None = None,
        status_code: int = http.HTTPStatus.NOT_FOUND,
        **kwargs,
    ):
        """Initialize a provider not found error.

        Args:
            provider: Name of the provider that wasn't found
            message: Error message (defaults to a standard message)
            status_code: HTTP status code (defaults to 404 Not Found)
            **kwargs: Additional arguments passed to ProviderError
        """
        message = message or f"Provider '{provider}' not found"
        super().__init__(message, provider, status_code, **kwargs)


class ProviderNotEnabledError(ProviderError):
    """Error raised when a requested provider is not enabled."""

    def __init__(
        self,
        provider: str,
        message: str | None = None,
        status_code: int = http.HTTPStatus.SERVICE_UNAVAILABLE,
        **kwargs,
    ):
        """Initialize a provider not enabled error.

        Args:
            provider: Name of the disabled provider
            message: Error message (defaults to a standard message)
            status_code: HTTP status code (defaults to 503 Service Unavailable)
            **kwargs: Additional arguments passed to ProviderError
        """
        message = message or f"Provider '{provider}' is not enabled"
        super().__init__(message, provider, status_code, **kwargs)


class ProviderInitializationError(ProviderError):
    """Error raised when a provider fails to initialize."""

    def __init__(
        self,
        provider: str,
        message: str | None = None,
        status_code: int = http.HTTPStatus.INTERNAL_SERVER_ERROR,
        **kwargs,
    ):
        """Initialize a provider initialization error.

        Args:
            provider: Name of the provider that failed to initialize
            message: Error message (defaults to a standard message)
            status_code: HTTP status code (defaults to 500 Internal Server Error)
            **kwargs: Additional arguments passed to ProviderError
        """
        message = message or f"Failed to initialize provider '{provider}'"
        super().__init__(message, provider, status_code, **kwargs)


class ProviderTimeoutError(ProviderError):
    """Error raised when a provider operation times out."""

    def __init__(
        self,
        provider: str,
        operation: str | None = None,
        timeout: float | None = None,
        message: str | None = None,
        status_code: int = http.HTTPStatus.GATEWAY_TIMEOUT,
        **kwargs,
    ):
        """Initialize a provider timeout error.

        Args:
            provider: Name of the provider that timed out
            operation: The operation that timed out (e.g., 'search', 'initialize')
            timeout: The timeout value in seconds
            message: Error message (defaults to a standard message)
            status_code: HTTP status code (defaults to 504 Gateway Timeout)
            **kwargs: Additional arguments passed to ProviderError
        """
        details = kwargs.pop("details", {})

        if operation:
            details["operation"] = operation
        if timeout:
            details["timeout_seconds"] = timeout

        # Generate default message if not provided
        if message is None:
            message = f"Operation timed out for provider '{provider}'"
            if operation:
                message = f"{operation.capitalize()} operation timed out for provider '{provider}'"
            if timeout:
                message += f" after {timeout} seconds"

        super().__init__(message, provider, status_code, details=details, **kwargs)


class ProviderRateLimitError(ProviderError):
    """Error raised when a provider's rate limit is exceeded."""

    def __init__(
        self,
        provider: str,
        limit_type: str | None = None,
        retry_after: float | None = None,
        message: str | None = None,
        status_code: int = http.HTTPStatus.TOO_MANY_REQUESTS,
        **kwargs,
    ):
        """Initialize a provider rate limit error.

        Args:
            provider: Name of the provider that was rate limited
            limit_type: Type of rate limit that was exceeded
            retry_after: Suggested retry delay in seconds
            message: Error message (defaults to a standard message)
            status_code: HTTP status code (defaults to 429 Too Many Requests)
            **kwargs: Additional arguments passed to ProviderError
        """
        details = kwargs.pop("details", {})

        if limit_type:
            details["limit_type"] = limit_type
        if retry_after:
            details["retry_after_seconds"] = retry_after

        if message is None:
            message = f"Rate limit exceeded for provider '{provider}'"
            if limit_type:
                message = f"{limit_type.capitalize()} rate limit exceeded for provider '{provider}'"
            if retry_after:
                message += f", retry after {retry_after} seconds"

        super().__init__(message, provider, status_code, details=details, **kwargs)


class ProviderAuthenticationError(ProviderError):
    """Error raised when provider authentication fails."""

    def __init__(
        self,
        provider: str,
        message: str | None = None,
        status_code: int = http.HTTPStatus.UNAUTHORIZED,
        **kwargs,
    ):
        """Initialize a provider authentication error.

        Args:
            provider: Name of the provider with authentication issues
            message: Error message (defaults to a standard message)
            status_code: HTTP status code (defaults to 401 Unauthorized)
            **kwargs: Additional arguments passed to ProviderError
        """
        message = message or f"Authentication failed for provider '{provider}'"
        super().__init__(message, provider, status_code, **kwargs)


class ProviderQuotaExceededError(ProviderError):
    """Error raised when a provider's quota is exceeded."""

    def __init__(
        self,
        provider: str,
        quota_type: str | None = None,
        message: str | None = None,
        status_code: int = http.HTTPStatus.PAYMENT_REQUIRED,
        **kwargs,
    ):
        """Initialize a provider quota exceeded error.

        Args:
            provider: Name of the provider with exceeded quota
            quota_type: Type of quota that was exceeded (e.g., 'daily', 'monthly')
            message: Error message (defaults to a standard message)
            status_code: HTTP status code (defaults to 402 Payment Required)
            **kwargs: Additional arguments passed to ProviderError
        """
        details = kwargs.pop("details", {})

        if quota_type:
            details["quota_type"] = quota_type

        if message is None:
            message = f"Quota exceeded for provider '{provider}'"
            if quota_type:
                message = f"{quota_type.capitalize()} quota exceeded for provider '{provider}'"

        super().__init__(message, provider, status_code, details=details, **kwargs)


class ProviderServiceError(ProviderError):
    """Error raised when a provider's service encounters an error."""

    def __init__(
        self,
        provider: str,
        message: str | None = None,
        status_code: int = http.HTTPStatus.BAD_GATEWAY,
        **kwargs,
    ):
        """Initialize a provider service error.

        Args:
            provider: Name of the provider with the service error
            message: Error message (defaults to a standard message)
            status_code: HTTP status code (defaults to 502 Bad Gateway)
            **kwargs: Additional arguments passed to ProviderError
        """
        message = message or f"Service error occurred for provider '{provider}'"
        super().__init__(message, provider, status_code, **kwargs)


# Query-related errors


class QueryError(SearchError):
    """Base class for errors related to search queries."""

    def __init__(
        self,
        message: str,
        query: str | None = None,
        status_code: int = http.HTTPStatus.BAD_REQUEST,
        **kwargs,
    ):
        """Initialize a query error.

        Args:
            message: Error message
            query: The problematic query string
            status_code: HTTP status code (defaults to 400 Bad Request)
            **kwargs: Additional arguments passed to SearchError
        """
        details = kwargs.pop("details", {})

        if query:
            details["query"] = query

        super().__init__(message, status_code=status_code, details=details, **kwargs)


class QueryValidationError(QueryError):
    """Error raised when a query fails validation."""

    def __init__(
        self,
        message: str,
        query: str | None = None,
        validation_errors: list[str] | None = None,
        **kwargs,
    ):
        """Initialize a query validation error.

        Args:
            message: Error message
            query: The invalid query string
            validation_errors: List of specific validation errors
            **kwargs: Additional arguments passed to QueryError
        """
        details = kwargs.pop("details", {})

        if validation_errors:
            details["validation_errors"] = validation_errors

        super().__init__(message, query, details=details, **kwargs)


class QueryTooComplexError(QueryError):
    """Error raised when a query is too complex to process."""

    def __init__(
        self,
        message: str | None = None,
        query: str | None = None,
        complexity_factors: dict[str, Any] | None = None,
        **kwargs,
    ):
        """Initialize a query too complex error.

        Args:
            message: Error message (defaults to a standard message)
            query: The complex query string
            complexity_factors: Dictionary of factors that made the query complex
            **kwargs: Additional arguments passed to QueryError
        """
        details = kwargs.pop("details", {})

        if complexity_factors:
            details["complexity_factors"] = complexity_factors

        message = message or "Query is too complex to process"

        super().__init__(message, query, details=details, **kwargs)


class QueryBudgetExceededError(QueryError):
    """Error raised when a query would exceed the allocated budget."""

    def __init__(
        self,
        message: str | None = None,
        query: str | None = None,
        budget: float | None = None,
        estimated_cost: float | None = None,
        status_code: int = http.HTTPStatus.PAYMENT_REQUIRED,
        **kwargs,
    ):
        """Initialize a query budget exceeded error.

        Args:
            message: Error message (defaults to a standard message)
            query: The query string
            budget: The maximum allowed budget
            estimated_cost: The estimated cost of the query
            status_code: HTTP status code (defaults to 402 Payment Required)
            **kwargs: Additional arguments passed to QueryError
        """
        details = kwargs.pop("details", {})

        if budget:
            details["budget"] = budget
        if estimated_cost:
            details["estimated_cost"] = estimated_cost

        if message is None:
            message = "Query would exceed allocated budget"
            if budget and estimated_cost:
                message = f"Query would cost {estimated_cost} but budget is {budget}"

        super().__init__(
            message, query, status_code=status_code, details=details, **kwargs
        )


# Router-related errors


class RouterError(SearchError):
    """Base class for errors related to query routing."""

    def __init__(
        self,
        message: str,
        status_code: int = http.HTTPStatus.INTERNAL_SERVER_ERROR,
        **kwargs,
    ):
        """Initialize a router error.

        Args:
            message: Error message
            status_code: HTTP status code (defaults to 500 Internal Server Error)
            **kwargs: Additional arguments passed to SearchError
        """
        super().__init__(message, status_code=status_code, **kwargs)


class NoProvidersAvailableError(RouterError):
    """Error raised when no providers are available for a query."""

    def __init__(
        self,
        message: str | None = None,
        query: str | None = None,
        status_code: int = http.HTTPStatus.SERVICE_UNAVAILABLE,
        **kwargs,
    ):
        """Initialize a no providers available error.

        Args:
            message: Error message (defaults to a standard message)
            query: The query string
            status_code: HTTP status code (defaults to 503 Service Unavailable)
            **kwargs: Additional arguments passed to RouterError
        """
        details = kwargs.pop("details", {})

        if query:
            details["query"] = query

        message = message or "No search providers are available to handle the query"

        super().__init__(message, status_code=status_code, details=details, **kwargs)


class CircuitBreakerOpenError(RouterError):
    """Error raised when a circuit breaker is open for a provider."""

    def __init__(
        self,
        provider: str,
        message: str | None = None,
        retry_after: float | None = None,
        status_code: int = http.HTTPStatus.SERVICE_UNAVAILABLE,
        **kwargs,
    ):
        """Initialize a circuit breaker open error.

        Args:
            provider: Name of the provider with the open circuit breaker
            message: Error message (defaults to a standard message)
            retry_after: Seconds until the circuit breaker may close
            status_code: HTTP status code (defaults to 503 Service Unavailable)
            **kwargs: Additional arguments passed to RouterError
        """
        details = kwargs.pop("details", {})
        details["provider"] = provider

        if retry_after:
            details["retry_after_seconds"] = retry_after

        if message is None:
            message = f"Circuit breaker is open for provider '{provider}'"
            if retry_after:
                message += f", retry after {retry_after} seconds"

        super().__init__(message, status_code=status_code, details=details, **kwargs)


class RoutingStrategyError(RouterError):
    """Error raised when a routing strategy fails."""

    def __init__(self, strategy: str, message: str | None = None, **kwargs):
        """Initialize a routing strategy error.

        Args:
            strategy: Name of the routing strategy that failed
            message: Error message (defaults to a standard message)
            **kwargs: Additional arguments passed to RouterError
        """
        details = kwargs.pop("details", {})
        details["strategy"] = strategy

        message = message or f"Routing strategy '{strategy}' failed"

        super().__init__(message, details=details, **kwargs)


# Configuration errors


class ConfigurationError(SearchError):
    """Error raised when there's an issue with the application configuration."""

    def __init__(
        self,
        message: str,
        config_key: str | None = None,
        status_code: int = http.HTTPStatus.INTERNAL_SERVER_ERROR,
        **kwargs,
    ):
        """Initialize a configuration error.

        Args:
            message: Error message
            config_key: The configuration key with the issue
            status_code: HTTP status code (defaults to 500 Internal Server Error)
            **kwargs: Additional arguments passed to SearchError
        """
        details = kwargs.pop("details", {})

        if config_key:
            details["config_key"] = config_key

        super().__init__(message, status_code=status_code, details=details, **kwargs)


class MissingConfigurationError(ConfigurationError):
    """Error raised when a required configuration value is missing."""

    def __init__(self, config_key: str, message: str | None = None, **kwargs):
        """Initialize a missing configuration error.

        Args:
            config_key: The missing configuration key
            message: Error message (defaults to a standard message)
            **kwargs: Additional arguments passed to ConfigurationError
        """
        message = message or f"Required configuration '{config_key}' is missing"
        super().__init__(message, config_key, **kwargs)


class InvalidConfigurationError(ConfigurationError):
    """Error raised when a configuration value is invalid."""

    def __init__(
        self, config_key: str, value: Any, message: str | None = None, **kwargs
    ):
        """Initialize an invalid configuration error.

        Args:
            config_key: The invalid configuration key
            value: The invalid value
            message: Error message (defaults to a standard message)
            **kwargs: Additional arguments passed to ConfigurationError
        """
        details = kwargs.pop("details", {})
        details["value"] = str(value)

        message = message or f"Configuration '{config_key}' has invalid value: {value}"

        super().__init__(message, config_key, details=details, **kwargs)


# Authentication and authorization errors


class AuthenticationError(SearchError):
    """Error raised when authentication fails."""

    def __init__(
        self,
        message: str | None = None,
        status_code: int = http.HTTPStatus.UNAUTHORIZED,
        **kwargs,
    ):
        """Initialize an authentication error.

        Args:
            message: Error message (defaults to a standard message)
            status_code: HTTP status code (defaults to 401 Unauthorized)
            **kwargs: Additional arguments passed to SearchError
        """
        message = message or "Authentication failed"
        super().__init__(message, status_code=status_code, **kwargs)


class AuthorizationError(SearchError):
    """Error raised when authorization fails."""

    def __init__(
        self,
        message: str | None = None,
        required_permission: str | None = None,
        status_code: int = http.HTTPStatus.FORBIDDEN,
        **kwargs,
    ):
        """Initialize an authorization error.

        Args:
            message: Error message (defaults to a standard message)
            required_permission: The permission that was missing
            status_code: HTTP status code (defaults to 403 Forbidden)
            **kwargs: Additional arguments passed to SearchError
        """
        details = kwargs.pop("details", {})

        if required_permission:
            details["required_permission"] = required_permission

        if message is None:
            message = "Not authorized to perform this action"
            if required_permission:
                message = f"Missing required permission: {required_permission}"

        super().__init__(message, status_code=status_code, details=details, **kwargs)


# Network and I/O errors


class NetworkError(SearchError):
    """Error raised when a network operation fails."""

    def __init__(
        self,
        message: str,
        url: str | None = None,
        status_code: int = http.HTTPStatus.BAD_GATEWAY,
        **kwargs,
    ):
        """Initialize a network error.

        Args:
            message: Error message
            url: The URL that failed
            status_code: HTTP status code (defaults to 502 Bad Gateway)
            **kwargs: Additional arguments passed to SearchError
        """
        details = kwargs.pop("details", {})

        if url:
            details["url"] = url

        super().__init__(message, status_code=status_code, details=details, **kwargs)


class NetworkConnectionError(NetworkError):
    """Error raised when a connection cannot be established."""

    def __init__(self, message: str | None = None, url: str | None = None, **kwargs):
        """Initialize a connection error.

        Args:
            message: Error message (defaults to a standard message)
            url: The URL that couldn't be connected to
            **kwargs: Additional arguments passed to NetworkError
        """
        if message is None:
            message = "Failed to establish connection"
            if url:
                message = f"Failed to establish connection to {url}"

        super().__init__(message, url, **kwargs)


class NetworkTimeoutError(NetworkError):
    """Error raised when a network operation times out."""

    def __init__(
        self,
        message: str | None = None,
        url: str | None = None,
        timeout: float | None = None,
        status_code: int = http.HTTPStatus.GATEWAY_TIMEOUT,
        **kwargs,
    ):
        """Initialize a timeout error.

        Args:
            message: Error message (defaults to a standard message)
            url: The URL that timed out
            timeout: The timeout value in seconds
            status_code: HTTP status code (defaults to 504 Gateway Timeout)
            **kwargs: Additional arguments passed to NetworkError
        """
        details = kwargs.pop("details", {})

        if timeout:
            details["timeout_seconds"] = timeout

        if message is None:
            message = "Network operation timed out"
            if url:
                message = f"Request to {url} timed out"
            if timeout:
                message += f" after {timeout} seconds"

        super().__init__(
            message, url, status_code=status_code, details=details, **kwargs
        )


# Utility functions


def format_exception(e: Exception) -> dict[str, Any]:
    """Format an exception for structured logging.

    Args:
        e: The exception to format

    Returns:
        A dictionary containing error details suitable for logging
    """
    if isinstance(e, SearchError):
        result = e.to_dict()
        result["traceback"] = traceback.format_exc()
        return result

    return {
        "error_type": e.__class__.__name__,
        "message": str(e),
        "traceback": traceback.format_exc(),
    }


def http_error_response(
    error: Exception | str,
    status_code: int = http.HTTPStatus.INTERNAL_SERVER_ERROR,
    **kwargs,
) -> dict[str, Any]:
    """Convert an error to a standardized HTTP error response.

    Args:
        error: The error (either an exception instance or a string message)
        status_code: HTTP status code to use (defaults to 500)
        **kwargs: Additional fields to include in the response

    Returns:
        A dictionary suitable for returning as a JSON error response
    """
    if isinstance(error, SearchError):
        response = error.to_dict()
        status_code = error.status_code
    elif isinstance(error, Exception):
        response = {
            "error_type": error.__class__.__name__,
            "message": str(error),
        }
    else:
        response = {
            "error_type": "Error",
            "message": str(error),
        }

    response["status_code"] = status_code

    # Add any additional fields
    for key, value in kwargs.items():
        if key not in response:
            response[key] = value

    return response
