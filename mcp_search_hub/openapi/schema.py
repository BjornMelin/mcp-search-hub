"""OpenAPI schema generation for MCP Search Hub."""

from typing import Any

from fastapi.openapi.utils import get_openapi

from ..utils.logging import get_logger

logger = get_logger(__name__)


def custom_openapi(app) -> dict[str, Any]:
    """Generate a custom OpenAPI schema for the FastMCP application.

    Args:
        app: FastAPI application instance

    Returns:
        Dict containing the OpenAPI schema
    """
    # Cache the schema to avoid regenerating it for every request
    if app.openapi_schema:
        return app.openapi_schema

    # Get the default OpenAPI schema
    openapi_schema = get_openapi(
        title="MCP Search Hub API",
        version="1.0.0",
        description=(
            "An intelligent multi-provider search aggregation server built on FastMCP 2.0. "
            "This API provides unified access to multiple search providers with intelligent "
            "routing, result combination, and error handling."
        ),
        routes=app.routes,
    )

    # Add server configuration (useful when behind a proxy)
    openapi_schema["servers"] = [{"url": "/", "description": "Default server"}]

    # Add tags metadata
    openapi_schema["tags"] = [
        {
            "name": "Search",
            "description": "Search operations across multiple providers",
        },
        {
            "name": "Health",
            "description": "Server health and status operations",
        },
        {
            "name": "Metrics",
            "description": "Performance metrics operations",
        },
        {
            "name": "Providers",
            "description": "Provider-specific operations",
        },
    ]

    # Add security scheme
    openapi_schema["components"] = openapi_schema.get("components", {})
    openapi_schema["components"]["securitySchemes"] = {
        "ApiKeyHeader": {
            "type": "apiKey",
            "in": "header",
            "name": "X-API-Key",
        }
    }

    # Add global security requirement (if authentication middleware is enabled)
    # This can be conditionally applied based on auth middleware enablement
    openapi_schema["security"] = [{"ApiKeyHeader": []}]

    # Store the schema
    app.openapi_schema = openapi_schema
    return app.openapi_schema


def get_schema_parameters(model_fields: dict[str, Any]) -> dict[str, Any]:
    """Convert model fields to OpenAPI parameters.

    Args:
        model_fields: Dictionary of model fields

    Returns:
        Dictionary of OpenAPI parameters
    """
    parameters = {}

    for field_name, field_info in model_fields.items():
        # Get the field type, description, and default value
        field_type = field_info.annotation
        field_description = field_info.description
        field_default = field_info.default

        # Convert field to OpenAPI parameter
        param = {
            "type": _get_openapi_type(field_type),
            "description": field_description or "",
        }

        # Add default value if it exists
        if field_default is not None:
            param["default"] = field_default

        # Add constraints if they exist
        if hasattr(field_info, "ge") and field_info.ge is not None:
            param["minimum"] = field_info.ge
        if hasattr(field_info, "le") and field_info.le is not None:
            param["maximum"] = field_info.le

        parameters[field_name] = param

    return parameters


def _get_openapi_type(python_type: Any) -> str:
    """Convert Python type to OpenAPI type.

    Args:
        python_type: Python type annotation

    Returns:
        OpenAPI type string
    """
    # Map Python types to OpenAPI types
    type_map = {
        str: "string",
        int: "integer",
        float: "number",
        bool: "boolean",
        dict: "object",
        list: "array",
    }

    # Handle Union types (e.g., str | None)
    if hasattr(python_type, "__origin__") and python_type.__origin__ is union_type:
        # Get the non-None types
        types = [t for t in python_type.__args__ if t is not type(None)]
        if len(types) == 1:
            return _get_openapi_type(types[0])
        return "object"  # Default for complex unions

    # Handle list types with specific item types
    if hasattr(python_type, "__origin__") and python_type.__origin__ is list:
        return "array"

    # Handle dict types
    if hasattr(python_type, "__origin__") and python_type.__origin__ is dict:
        return "object"

    # Default to string for unknown types
    return type_map.get(python_type, "string")


# Get the union type based on Python version
try:
    from types import UnionType

    union_type = UnionType
except ImportError:
    # For Python < 3.10
    from typing import Union

    union_type = Union
