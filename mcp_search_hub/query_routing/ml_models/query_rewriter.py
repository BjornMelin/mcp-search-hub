"""ML-powered query rewriting for improved search results."""

import logging
import re

from pydantic import BaseModel, Field

from ...models.query import SearchQuery
from .embedding import USE_ML, EmbeddingGenerator

logger = logging.getLogger(__name__)


class RewriteTemplate(BaseModel):
    """Template for query rewriting."""

    pattern: str = Field(..., description="Regex pattern to match")
    replacement: str = Field(..., description="Replacement template with $1, $2, etc.")
    content_types: list[str] = Field(
        default=["general"], description="Content types this template applies to"
    )
    priority: int = Field(
        default=1, description="Priority (higher numbers = higher priority)"
    )


class RewriteResult(BaseModel):
    """Result of query rewriting."""

    original_query: str = Field(..., description="The original query text")
    rewritten_query: str = Field(..., description="The rewritten query text")
    method: str = Field(
        ..., description="Method used for rewriting (template, similarity, expansion)"
    )
    confidence: float = Field(..., description="Confidence in the rewrite (0.0-1.0)")
    changes: str = Field(
        ..., description="Description of changes made during rewriting"
    )


class QueryRewriter:
    """Rewrites queries to improve search quality.

    The rewriter uses multiple strategies:
    1. Template-based rewrites for common patterns
    2. Similarity-based rewrites for semantic improvements
    3. Query expansion for adding relevant terms
    """

    def __init__(self):
        """Initialize the query rewriter."""
        self.embedding_generator = EmbeddingGenerator(
            model_name="all-MiniLM-L6-v2", cache_size=1000
        )
        self.rewrite_templates = self._initialize_rewrite_templates()
        self._success_cache = {}  # track successful rewrites

    def _initialize_rewrite_templates(self) -> list[RewriteTemplate]:
        """Initialize default rewrite templates."""
        templates = [
            # Question reformulation
            RewriteTemplate(
                pattern=r"^(?:can you |could you |please |)(tell me about|explain|describe) (.+)$",
                replacement=r"\2",
                content_types=["general", "academic", "technical"],
                priority=2,
            ),
            # Informal to formal
            RewriteTemplate(
                pattern=r"^(?:hey|hi|yo|) (?:can|could) (?:you|u|) (?:give me|show me|find|get) (.+)$",
                replacement=r"\1",
                content_types=["general"],
                priority=1,
            ),
            # Expand acronyms for technical queries
            RewriteTemplate(
                pattern=r"\b(API)\b",
                replacement=r"API application programming interface",
                content_types=["technical"],
                priority=3,
            ),
            RewriteTemplate(
                pattern=r"\b(ML)\b",
                replacement=r"ML machine learning",
                content_types=["technical", "academic"],
                priority=3,
            ),
            # Add scholarly terms for academic queries
            RewriteTemplate(
                pattern=r"^(research on|studies about|papers on) (.+)$",
                replacement=r"academic research papers journal articles \2",
                content_types=["academic"],
                priority=3,
            ),
            # Enhance business queries
            RewriteTemplate(
                pattern=r"^(info|information) (about|on) (.+) (company|business)$",
                replacement=r"\3 \4 financials revenue business model",
                content_types=["business"],
                priority=2,
            ),
            # Latest news
            RewriteTemplate(
                pattern=r"^(?:what are the |what's the |)(latest|recent|current) (?:news|update|info) (?:about|on) (.+)$",
                replacement=r"latest news \2 current events recent developments",
                content_types=["news"],
                priority=3,
            ),
            # Web content extraction enhancement
            RewriteTemplate(
                pattern=r"^(?:how to |)(extract|scrape|get) (?:content|data|information|text) (?:from|on) (.+)$",
                replacement=r"extract content \2 scrape website data",
                content_types=["web_content"],
                priority=3,
            ),
        ]
        return templates

    def rewrite(
        self, query: SearchQuery, content_type: str, rewrite_threshold: float = 0.6
    ) -> list[RewriteResult]:
        """Rewrite the query to improve search quality.

        Args:
            query: The original search query
            content_type: The detected content type
            rewrite_threshold: Only use rewrites with confidence above this threshold

        Returns:
            List of RewriteResults, sorted by confidence (highest first)
        """
        query_text = query.query
        results = []

        # Try template-based rewrites
        template_rewrites = self._apply_templates(query_text, content_type)
        results.extend(template_rewrites)

        # Try similarity-based rewrites if ML is enabled
        if USE_ML:
            similarity_rewrites = self._apply_similarity_rewrites(
                query_text, content_type
            )
            results.extend(similarity_rewrites)

            # Try query expansion for specific content types
            if content_type in ["academic", "technical", "business"]:
                expansion_rewrites = self._apply_query_expansion(
                    query_text, content_type
                )
                results.extend(expansion_rewrites)

        # Filter by threshold and remove duplicates
        results = [r for r in results if r.confidence >= rewrite_threshold]

        # Remove duplicates (keeping the highest confidence version)
        unique_results = {}
        for result in sorted(results, key=lambda x: x.confidence, reverse=True):
            if result.rewritten_query not in unique_results:
                unique_results[result.rewritten_query] = result

        # Sort by confidence (highest first)
        return sorted(unique_results.values(), key=lambda x: x.confidence, reverse=True)

    def _apply_templates(
        self, query_text: str, content_type: str
    ) -> list[RewriteResult]:
        """Apply template-based rewrites.

        Args:
            query_text: The original query text
            content_type: The detected content type

        Returns:
            List of RewriteResults from template-based rewrites
        """
        results = []
        query_lower = query_text.lower()

        # Filter templates by content type
        applicable_templates = [
            t for t in self.rewrite_templates if content_type in t.content_types
        ]

        # Sort by priority (highest first)
        applicable_templates.sort(key=lambda x: x.priority, reverse=True)

        for template in applicable_templates:
            try:
                # Check if the template matches
                match = re.match(template.pattern, query_lower, re.IGNORECASE)
                if not match:
                    continue

                # Apply the template
                rewritten = re.sub(
                    template.pattern,
                    template.replacement,
                    query_lower,
                    flags=re.IGNORECASE,
                )

                # Skip if no change
                if rewritten.strip() == query_lower.strip():
                    continue

                # Calculate confidence based on priority and change amount
                # Higher priority templates and more significant changes = higher confidence
                base_confidence = min(template.priority * 0.2, 0.8)
                change_ratio = 1 - (
                    len(set(rewritten.split()) & set(query_lower.split()))
                    / max(len(rewritten.split()), len(query_lower.split()))
                )
                confidence = base_confidence + (change_ratio * 0.2)

                # Generate change description
                if len(rewritten) > len(query_lower):
                    changes = "Added terms for better search context"
                elif len(rewritten) < len(query_lower):
                    changes = "Removed unnecessary words for more focused search"
                else:
                    changes = "Reformulated for better search precision"

                results.append(
                    RewriteResult(
                        original_query=query_text,
                        rewritten_query=rewritten,
                        method="template",
                        confidence=min(confidence, 0.95),  # Cap at 0.95
                        changes=changes,
                    )
                )

            except Exception as e:
                logger.error(f"Error applying template {template.pattern}: {e}")

        return results

    def _apply_similarity_rewrites(
        self, query_text: str, content_type: str
    ) -> list[RewriteResult]:
        """Apply similarity-based rewrites using embeddings.

        Args:
            query_text: The original query text
            content_type: The detected content type

        Returns:
            List of RewriteResults from similarity-based rewrites
        """
        # This is a simplified implementation - in a real system,
        # we would use a more sophisticated approach with a database
        # of successful query reformulations.

        # Check if we have successful rewrites for this content type in our cache
        if content_type not in self._success_cache:
            return []

        results = []

        # Get the embedding for this query
        query_embedding = self.embedding_generator.generate(query_text)

        # Check similarity with cached successful queries
        for cached_query, data in self._success_cache[content_type].items():
            try:
                similarity = self.embedding_generator.similarity(
                    query_text, cached_query
                )

                # If similar but not identical
                if 0.7 <= similarity < 0.98:
                    confidence = (
                        similarity * 0.8
                    )  # Scale confidence based on similarity

                    results.append(
                        RewriteResult(
                            original_query=query_text,
                            rewritten_query=data["rewritten"],
                            method="similarity",
                            confidence=confidence,
                            changes="Rewritten based on similar successful query",
                        )
                    )
            except Exception as e:
                logger.error(f"Error in similarity rewrite: {e}")

        return results

    def _apply_query_expansion(
        self, query_text: str, content_type: str
    ) -> list[RewriteResult]:
        """Apply query expansion to add relevant terms.

        Args:
            query_text: The original query text
            content_type: The detected content type

        Returns:
            List of RewriteResults from query expansion
        """
        # Define expansion terms per content type
        expansion_terms = {
            "academic": ["research", "study", "paper", "journal", "publication"],
            "technical": [
                "tutorial",
                "code",
                "example",
                "implementation",
                "documentation",
            ],
            "business": ["company", "market", "industry", "financial", "revenue"],
            "news": ["latest", "recent", "update", "report", "current"],
            "web_content": ["content", "extract", "scrape", "website", "data"],
        }

        results = []

        # Get terms for this content type
        terms = expansion_terms.get(content_type, [])
        if not terms:
            return results

        # Check if the query already contains these terms
        query_words = set(query_text.lower().split())

        # Filter out terms already in the query
        new_terms = [term for term in terms if term not in query_words]

        # Don't expand if no new terms or query is already long
        if not new_terms or len(query_words) > 10:
            return results

        # Select at most 2 terms for expansion
        selected_terms = new_terms[:2]

        # Create expanded query
        expanded_query = f"{query_text} {' '.join(selected_terms)}"

        results.append(
            RewriteResult(
                original_query=query_text,
                rewritten_query=expanded_query,
                method="expansion",
                confidence=0.7,  # Medium confidence for expansions
                changes=f"Added relevant terms: {', '.join(selected_terms)}",
            )
        )

        return results

    def record_success(
        self, query_text: str, rewritten_query: str, content_type: str
    ) -> None:
        """Record a successful query rewrite for future reference.

        Args:
            query_text: The original query text
            rewritten_query: The successful rewritten query
            content_type: The content type
        """
        if content_type not in self._success_cache:
            self._success_cache[content_type] = {}

        # Store the successful rewrite
        self._success_cache[content_type][query_text] = {
            "rewritten": rewritten_query,
            "success_count": self._success_cache.get(content_type, {})
            .get(query_text, {})
            .get("success_count", 0)
            + 1,
        }

        # Trim cache if it gets too large (keep the most successful rewrites)
        if len(self._success_cache[content_type]) > 1000:
            # Sort by success count and keep top 500
            sorted_items = sorted(
                self._success_cache[content_type].items(),
                key=lambda x: x[1]["success_count"],
                reverse=True,
            )
            self._success_cache[content_type] = dict(sorted_items[:500])
