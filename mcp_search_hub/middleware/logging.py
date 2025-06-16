"""Logging middleware for MCP Search Hub."""

import json
import time
import uuid
from collections.abc import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from ..utils.logging import get_logger

logger = get_logger(__name__)


class LoggingMiddleware(BaseHTTPMiddleware):
    """Middleware for centralized request/response logging."""

    def __init__(self, app, **options):
        """Initialize logging middleware.

        Args:
            app: ASGI application
            **options: Configuration options including:
                - log_level: Log level to use
                - include_headers: Whether to include headers in logs
                - include_body: Whether to include request/response body in logs
                - sensitive_headers: List of headers to redact
                - max_body_size: Max body size to log
        """
        super().__init__(app)
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

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process HTTP requests with logging.

        Args:
            request: The incoming HTTP request
            call_next: The next middleware or handler

        Returns:
            The response from downstream
        """
        # Generate a trace ID for this request
        trace_id = str(uuid.uuid4())

        # Store start time for duration calculation
        start_time = time.perf_counter()

        # Add trace context to the request
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
            log_data["headers"] = self._redact_sensitive_headers(dict(request.headers))

        # Log the request
        logger.info(f"HTTP Request: {json.dumps(log_data)}")

        # Call the next middleware/handler
        response = await call_next(request)

        # Calculate request duration
        duration_ms = (time.perf_counter() - start_time) * 1000

        # Log response
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
            log_data["headers"] = self._redact_sensitive_headers(dict(response.headers))

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

        return response
