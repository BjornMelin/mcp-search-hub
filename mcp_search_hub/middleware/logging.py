"""Logging middleware for MCP Search Hub."""

import json
import time
import uuid
from typing import Any

from fastmcp import Context
from starlette.requests import Request
from starlette.responses import Response

from ..utils.logging import get_logger
from .base import BaseMiddleware

logger = get_logger(__name__)


class LoggingMiddleware(BaseMiddleware):
    """Middleware for centralized request/response logging."""

    def _initialize(self, **options):
        """Initialize logging middleware.

        Args:
            **options: Configuration options including:
                - log_level: Log level to use
                - include_headers: Whether to include headers in logs
                - include_body: Whether to include request/response body in logs
                - sensitive_headers: List of headers to redact
                - max_body_size: Max body size to log
        """
        self.order = options.get("order", 5)  # Logging should run first
        self.log_level = options.get("log_level", "INFO")
        self.include_headers = options.get("include_headers", True)
        self.include_body = options.get("include_body", False)
        self.sensitive_headers = options.get(
            "sensitive_headers", ["authorization", "x-api-key", "cookie", "set-cookie"]
        )
        self.max_body_size = options.get("max_body_size", 1024)  # 1 KB

        logger.info(
            f"Logging middleware initialized with log level {self.log_level}, "
            f"include_headers={self.include_headers}, include_body={self.include_body}"
        )

    def _redact_sensitive_headers(self, headers: dict[str, str]) -> dict[str, str]:
        """Redact sensitive headers.

        Args:
            headers: Headers dictionary

        Returns:
            Redacted headers dictionary
        """
        redacted = {}
        for key, value in headers.items():
            if key.lower() in self.sensitive_headers:
                redacted[key] = "REDACTED"
            else:
                redacted[key] = value
        return redacted

    def _truncate_body(self, body: str) -> str:
        """Truncate body if too large.

        Args:
            body: Request or response body

        Returns:
            Truncated body
        """
        if len(body) > self.max_body_size:
            return (
                body[: self.max_body_size] + f"... [truncated, {len(body)} bytes total]"
            )
        return body

    async def process_request(
        self, request: Any, context: Context | None = None
    ) -> Any:
        """Process and log the incoming request.

        Args:
            request: The incoming request (HTTP or tool params)
            context: Optional Context object for tool requests

        Returns:
            The request with trace_id added
        """
        # Generate a trace ID for this request
        trace_id = str(uuid.uuid4())

        # Store start time for duration calculation
        start_time = time.perf_counter()

        # Add trace context to the request
        if isinstance(request, Request):
            # For HTTP requests
            request.state.trace_id = trace_id
            request.state.start_time = start_time

            # Log request
            log_data = {
                "trace_id": trace_id,
                "timestamp": time.time(),
                "type": "request",
                "method": request.method,
                "path": request.url.path,
                "query": dict(request.query_params),
                "client_ip": request.client.host if request.client else "unknown",
            }

            # Add headers if configured
            if self.include_headers and request.headers:
                log_data["headers"] = self._redact_sensitive_headers(
                    dict(request.headers)
                )

            # Log the request
            logger.info(f"HTTP Request: {json.dumps(log_data)}")

        elif context:
            # For tool requests
            if not hasattr(context, "state"):
                context.state = {}
            context.state["trace_id"] = trace_id
            context.state["start_time"] = start_time

            # Log tool request
            tool_name = "unknown"
            if isinstance(request, dict) and "tool_name" in request:
                tool_name = request["tool_name"]

            log_data = {
                "trace_id": trace_id,
                "timestamp": time.time(),
                "type": "tool_request",
                "tool": tool_name,
            }

            # Include parameters if configured
            if self.include_body:
                # Make a safe copy of params for logging
                safe_params = {}
                if isinstance(request, dict):
                    for k, v in request.items():
                        if k.lower() in ["api_key", "key", "secret"]:
                            safe_params[k] = "REDACTED"
                        else:
                            safe_params[k] = v
                log_data["params"] = safe_params

            # Log the tool request
            logger.info(f"Tool Request: {json.dumps(log_data)}")

        return request

    async def process_response(
        self, response: Any, request: Any, context: Context | None = None
    ) -> Any:
        """Process and log the outgoing response.

        Args:
            response: The response object
            request: The original request
            context: Optional Context object

        Returns:
            The unmodified response
        """
        # Calculate request duration
        start_time = None
        trace_id = None

        if isinstance(request, Request) and hasattr(request, "state"):
            start_time = getattr(request.state, "start_time", None)
            trace_id = getattr(request.state, "trace_id", None)
        elif context and hasattr(context, "state"):
            start_time = context.state.get("start_time")
            trace_id = context.state.get("trace_id")

        if not start_time or not trace_id:
            # Can't properly log without trace info
            return response

        duration_ms = (time.perf_counter() - start_time) * 1000

        # Prepare log data
        if isinstance(request, Request):
            # For HTTP responses
            status_code = None
            if isinstance(response, Response):
                status_code = response.status_code

            log_data = {
                "trace_id": trace_id,
                "timestamp": time.time(),
                "type": "response",
                "duration_ms": round(duration_ms, 2),
                "status": status_code,
                "path": request.url.path,
                "method": request.method,
            }

            # Add headers if configured
            if self.include_headers and hasattr(response, "headers"):
                log_data["headers"] = self._redact_sensitive_headers(
                    dict(response.headers)
                )

            # Log response body if configured and possible
            if self.include_body and hasattr(response, "body"):
                try:
                    body = response.body.decode("utf-8")
                    log_data["body"] = self._truncate_body(body)
                except Exception:
                    log_data["body"] = "[binary or non-utf8 content]"

            # Log the response
            log_msg = f"HTTP Response: {json.dumps(log_data)}"
            if status_code and status_code >= 500:
                logger.error(log_msg)
            elif status_code and status_code >= 400:
                logger.warning(log_msg)
            else:
                logger.info(log_msg)

        else:
            # For tool responses
            tool_name = "unknown"
            if isinstance(request, dict) and "tool_name" in request:
                tool_name = request["tool_name"]

            log_data = {
                "trace_id": trace_id,
                "timestamp": time.time(),
                "type": "tool_response",
                "tool": tool_name,
                "duration_ms": round(duration_ms, 2),
            }

            # Include response data if configured
            if self.include_body:
                # Try to create a safe version of the response for logging
                try:
                    # Check if the response is JSONable
                    json.dumps(response)
                    log_data["response"] = self._truncate_body(str(response))
                except (TypeError, ValueError, OverflowError):
                    # Non-serializable response
                    log_data["response"] = str(type(response))

            # Log the tool response
            logger.info(f"Tool Response: {json.dumps(log_data)}")

        return response
