"""Query models."""

from pydantic import BaseModel, Field


class SearchQuery(BaseModel):
    """A search query submitted to the system."""

    query: str = Field(..., description="The search query text")
    advanced: bool = Field(
        False, description="Whether to use advanced search capabilities"
    )
    max_results: int = Field(
        10, description="Maximum number of results to return", ge=1, le=100
    )
    content_type: str | None = Field(
        None, description="Optional explicit content type hint"
    )
    providers: list[str] | None = Field(
        None, description="Optional explicit provider selection"
    )
    budget: float | None = Field(None, description="Optional budget constraint in USD")
    timeout_ms: int = Field(
        5000, description="Timeout in milliseconds", ge=1000, le=30000
    )
    raw_content: bool = Field(
        False, description="Whether to include raw content in search results"
    )
    routing_strategy: str | None = Field(
        None,
        description="Execution strategy: 'parallel' (faster) or 'cascade' (more reliable)",
    )
    routing_hints: str | None = Field(
        None,
        description="Natural language guidance for routing decisions (e.g., 'prioritize recent news')",
    )


class QueryFeatures(BaseModel):
    """Features extracted from a search query for routing."""

    length: int = Field(..., description="Length of the query in characters")
    word_count: int = Field(..., description="Number of words in the query")
    contains_question: bool = Field(
        ..., description="Whether the query contains a question"
    )
    content_type: str = Field(..., description="Detected content type")
    time_sensitivity: float = Field(..., description="Time sensitivity score (0.0-1.0)")
    complexity: float = Field(..., description="Query complexity score (0.0-1.0)")
    factual_nature: float = Field(..., description="Factual nature score (0.0-1.0)")
