"""ML-driven query partitioner for multi-provider execution."""

import logging
import re

from pydantic import BaseModel, Field

from ...models.query import SearchQuery
from .embedding import USE_ML, EmbeddingGenerator

logger = logging.getLogger(__name__)


class QueryPart(BaseModel):
    """A part of a partitioned query."""

    text: str = Field(..., description="The partitioned query text")
    content_type: str = Field(..., description="Content type for this part")
    importance: float = Field(
        ..., description="Importance score for this part (0.0-1.0)"
    )
    providers: list[str] = Field(
        default_factory=list, description="Recommended providers for this part"
    )


class PartitionResult(BaseModel):
    """Result of query partitioning."""

    original_query: str = Field(..., description="The original query text")
    parts: list[QueryPart] = Field(..., description="The partitioned query parts")
    method: str = Field(
        ..., description="Method used for partitioning (ml, rule_based, or fallback)"
    )
    confidence: float = Field(
        ..., description="Confidence in the partitioning (0.0-1.0)"
    )


class QueryPartitioner:
    """Partitions complex queries into parts for multi-provider execution.

    The partitioner identifies different aspects or intents within a query
    and breaks it down into parts that can be routed to different providers.
    """

    def __init__(self):
        """Initialize the query partitioner."""
        self.embedding_generator = EmbeddingGenerator(
            model_name="all-MiniLM-L6-v2", cache_size=1000
        )
        self._content_classifier = None

    @property
    def content_classifier(self):
        """Lazily load the content classifier."""
        if self._content_classifier is None:
            from .content_classifier import ContentClassifier

            self._content_classifier = ContentClassifier()
        return self._content_classifier

    def partition(self, query: SearchQuery) -> PartitionResult:
        """Partition the query into parts for multi-provider execution.

        Args:
            query: The search query to partition

        Returns:
            PartitionResult with partitioned query parts
        """
        query_text = query.query

        # Don't partition short queries
        if len(query_text.split()) < 5:
            # Use the content classifier to determine the type
            classification = self.content_classifier.classify(query_text)

            return PartitionResult(
                original_query=query_text,
                parts=[
                    QueryPart(
                        text=query_text,
                        content_type=classification.content_type,
                        importance=1.0,
                    )
                ],
                method="none",
                confidence=1.0,
            )

        if not USE_ML:
            # Use rule-based partitioning if ML is disabled
            parts = self._rule_based_partition(query_text)
            return PartitionResult(
                original_query=query_text,
                parts=parts,
                method="rule_based",
                confidence=0.7,
            )

        try:
            # ML-based partitioning
            if self._is_multi_part_query(query_text):
                parts = self._ml_partition(query_text)
                confidence = 0.8 if len(parts) > 1 else 0.6
                return PartitionResult(
                    original_query=query_text,
                    parts=parts,
                    method="ml",
                    confidence=confidence,
                )
            # Single part query using ML content classifier
            classification = self.content_classifier.classify(query_text)
            return PartitionResult(
                original_query=query_text,
                parts=[
                    QueryPart(
                        text=query_text,
                        content_type=classification.content_type,
                        importance=1.0,
                    )
                ],
                method="ml_single",
                confidence=classification.confidence,
            )
        except Exception as e:
            logger.error(f"Error in ML query partitioning: {e}")
            # Fall back to rule-based
            parts = self._rule_based_partition(query_text)
            return PartitionResult(
                original_query=query_text,
                parts=parts,
                method="rule_based_fallback",
                confidence=0.6,
            )

    def _is_multi_part_query(self, query_text: str) -> bool:
        """Determine if a query should be partitioned.

        Args:
            query_text: The query text to check

        Returns:
            True if the query should be partitioned
        """
        # Look for conjunction indicators
        conjunction_patterns = [
            r"\band\b",
            r"\bversus\b|\bvs\b|\bcompared to\b|\bcompare\b",
            r"\balso\b|\bas well as\b|\bin addition to\b",
            r"\bboth\b.*\band\b",
            r"\bnot only\b.*\bbut also\b",
            r"\bfirst\b.*\bthen\b|\binitially\b.*\bfollowed by\b",
            r";|,",  # Semicolons or commas can indicate separate queries
            r"\balternatively\b|\binstead\b",
        ]

        for pattern in conjunction_patterns:
            if re.search(pattern, query_text, re.IGNORECASE):
                return True

        # Check for question stacking (multiple question marks or multiple question words)
        if query_text.count("?") > 1:
            return True

        question_words = ["what", "where", "when", "who", "why", "how"]
        question_word_count = sum(
            1 for word in question_words if f" {word} " in f" {query_text.lower()} "
        )
        if question_word_count > 1:
            return True

        # Check for clear breaks in the query intent
        if len(query_text.split()) > 12:  # Only check longer queries
            # Compute local cosine similarities between sliding windows of words
            words = query_text.split()
            window_size = 5

            if len(words) <= window_size * 2:
                return False

            # Create windows and compute embeddings
            windows = [
                " ".join(words[i : i + window_size])
                for i in range(0, len(words) - window_size + 1, window_size // 2)
            ]

            if len(windows) < 2:
                return False

            # Detect significant shifts in meaning between adjacent windows
            for i in range(len(windows) - 1):
                similarity = self.embedding_generator.similarity(
                    windows[i], windows[i + 1]
                )
                if similarity < 0.6:  # Low similarity indicates a topic shift
                    return True

        return False

    def _ml_partition(self, query_text: str) -> list[QueryPart]:
        """Partition the query using ML techniques.

        Args:
            query_text: The query text to partition

        Returns:
            List of QueryPart objects
        """
        # Try to split by explicit conjunctions first
        parts = self._split_by_conjunctions(query_text)

        if len(parts) == 1:
            # Try sentence-based splitting for queries without explicit conjunctions
            parts = self._split_by_sentences(query_text)

        # Classify and rank each part
        classified_parts = []

        for i, part_text in enumerate(parts):
            try:
                classification = self.content_classifier.classify(part_text)

                # Calculate importance based on position, length, and content type
                # Earlier parts and longer parts are generally more important
                position_factor = 1.0 - (
                    i / len(parts) * 0.3
                )  # 1.0 → 0.7 based on position
                length_factor = (
                    min(len(part_text) / 100, 0.5) + 0.5
                )  # 0.5 → 1.0 based on length

                # Content type factor (academic and technical queries get higher importance)
                type_factor = 1.0
                if classification.content_type in ["academic", "technical"]:
                    type_factor = 1.2
                elif classification.content_type in ["news", "business"]:
                    type_factor = 1.1

                importance = min(position_factor * length_factor * type_factor, 1.0)

                classified_parts.append(
                    QueryPart(
                        text=part_text,
                        content_type=classification.content_type,
                        importance=importance,
                        providers=[],  # Will be filled by router
                    )
                )
            except Exception as e:
                logger.error(f"Error classifying part '{part_text}': {e}")
                # Add a default part with lower confidence
                classified_parts.append(
                    QueryPart(
                        text=part_text,
                        content_type="general",
                        importance=0.5,
                        providers=[],
                    )
                )

        # Sort by importance (highest first)
        classified_parts.sort(key=lambda x: x.importance, reverse=True)

        return classified_parts

    def _split_by_conjunctions(self, query_text: str) -> list[str]:
        """Split the query by conjunction patterns.

        Args:
            query_text: The query text to split

        Returns:
            List of split parts
        """
        # Define patterns that indicate separate parts
        split_patterns = [
            (r"\band also\b|\bas well as\b|\bin addition\b", 0.9),
            (r"\bcompared to\b|\bversus\b|\bvs\b", 0.9),
            (r"\;", 0.9),  # Semicolons strongly indicate separate parts
            (r"\bbut\b", 0.8),
            (r"\bwhile\b", 0.7),
            (r"\, and\b", 0.8),
            (r"\, but\b", 0.8),
            (r"\balternatively\b", 0.8),
        ]

        # Try each pattern in order of confidence
        for pattern, confidence in sorted(
            split_patterns, key=lambda x: x[1], reverse=True
        ):
            if re.search(pattern, query_text, re.IGNORECASE):
                # Split by the pattern
                split_text = re.split(pattern, query_text, flags=re.IGNORECASE)

                # Clean and filter parts
                parts = [part.strip() for part in split_text if part.strip()]

                # Only use the split if it produces meaningful parts
                if all(len(part.split()) >= 3 for part in parts):
                    return parts

        # No meaningful splits found
        return [query_text]

    def _split_by_sentences(self, query_text: str) -> list[str]:
        """Split the query into sentences.

        Args:
            query_text: The query text to split

        Returns:
            List of sentences
        """
        # Simple sentence splitting
        sentences = re.split(r"[.!?]", query_text)
        sentences = [s.strip() for s in sentences if s.strip()]

        # Only return sentences if we have multiple meaningful ones
        if len(sentences) > 1 and all(len(s.split()) >= 3 for s in sentences):
            return sentences

        return [query_text]

    def _rule_based_partition(self, query_text: str) -> list[QueryPart]:
        """Rule-based query partitioning as fallback.

        Args:
            query_text: The query text to partition

        Returns:
            List of QueryPart objects
        """
        # Simple rule-based splitting by conjunctions
        if re.search(r"\band\b|;|,", query_text):
            parts = re.split(r"\band\b|;|,", query_text)
            parts = [part.strip() for part in parts if len(part.strip()) > 0]

            # Only use parts if they're meaningful
            if len(parts) > 1 and all(len(part.split()) >= 2 for part in parts):
                result_parts = []

                for i, part_text in enumerate(parts):
                    # Use fallback analyzer to detect content type
                    from ..analyzer import QueryAnalyzer

                    analyzer = QueryAnalyzer()
                    content_type = analyzer._detect_content_type(part_text)

                    # Simple importance based on position
                    importance = 1.0 - (i * 0.2)
                    importance = max(importance, 0.5)

                    result_parts.append(
                        QueryPart(
                            text=part_text,
                            content_type=content_type,
                            importance=importance,
                            providers=[],
                        )
                    )

                return result_parts

        # If no partitioning is possible, return the whole query
        from ..analyzer import QueryAnalyzer

        analyzer = QueryAnalyzer()
        content_type = analyzer._detect_content_type(query_text)

        return [
            QueryPart(
                text=query_text,
                content_type=content_type,
                importance=1.0,
                providers=[],
            )
        ]
