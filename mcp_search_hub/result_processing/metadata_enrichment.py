"""Metadata enrichment for search results.

Simple, focused module to extract and normalize metadata from search results.
"""

import re
from datetime import datetime
from urllib.parse import urlparse

import dateparser

from ..models.results import SearchResult


def enrich_result_metadata(result: SearchResult) -> None:
    """Extract and normalize metadata from a search result."""
    # Extract domain info first (needed for other metadata)
    if "source_domain" not in result.metadata:
        try:
            parsed_url = urlparse(result.url)
            domain = parsed_url.netloc.lower()
            # Remove www prefix if present
            domain = re.sub(r"^www\d?\.", "", domain)
            result.metadata["source_domain"] = domain

            # Extract organization name from domain
            domain_parts = domain.split(".")
            if len(domain_parts) >= 2 and domain_parts[-1] in [
                "com",
                "org",
                "net",
                "io",
            ]:
                # For commercial domains, use the subdomain
                org_name = domain_parts[-2].capitalize()
                # Convert kebab/snake case to title case
                if "-" in org_name:
                    org_name = " ".join(
                        word.capitalize() for word in org_name.split("-")
                    )
                result.metadata["organization"] = org_name
        except Exception:
            pass

    # Extract date info (from metadata, title, or snippet)
    if "normalized_date" not in result.metadata:
        # Use existing date or extract from content
        date_str = result.metadata.get("published_date")
        if not date_str:
            # Look for dates in title and snippet with common patterns
            patterns = [
                r"\d{4}-\d{1,2}-\d{1,2}",  # ISO format
                r"\d{1,2}/\d{1,2}/\d{4}",  # MM/DD/YYYY
                r"\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{4}",  # DD Mon YYYY
            ]

            for pattern in patterns:
                # Check title then snippet
                match = re.search(pattern, result.title)
                if not match:
                    match = re.search(pattern, result.snippet)
                if match:
                    date_str = match.group(0)
                    break

        # Parse the date if found
        if date_str:
            try:
                parsed_date = dateparser.parse(date_str)
                if parsed_date:
                    # Store several date formats
                    result.metadata["normalized_date"] = parsed_date.isoformat()
                    result.metadata["year"] = parsed_date.year
                    result.metadata["month"] = parsed_date.month
                    result.metadata["day"] = parsed_date.day
                    result.metadata["human_date"] = parsed_date.strftime("%B %d, %Y")

                    # Add relative time
                    now = datetime.now()
                    delta = now - parsed_date
                    if delta.days < 7:
                        result.metadata["relative_time"] = f"{delta.days} days ago"
                    elif delta.days < 30:
                        result.metadata["relative_time"] = (
                            f"{delta.days // 7} weeks ago"
                        )
                    elif delta.days < 365:
                        result.metadata["relative_time"] = (
                            f"{delta.days // 30} months ago"
                        )
                    else:
                        result.metadata["relative_time"] = (
                            f"{delta.days // 365} years ago"
                        )

                    # Set published_date if not already present
                    if "published_date" not in result.metadata:
                        result.metadata["published_date"] = parsed_date.isoformat()
            except Exception:
                pass

    # Calculate content metrics
    if "word_count" not in result.metadata:
        content = result.raw_content or result.snippet
        word_count = len(re.findall(r"\b\w+\b", content))
        result.metadata["word_count"] = word_count

        # Estimate reading time (225 words per minute)
        reading_time = max(1, round(word_count / 225))
        result.metadata["reading_time"] = reading_time
        result.metadata["reading_time_display"] = f"{reading_time} minute read"

    # Generate simple citation
    if "citation" not in result.metadata:
        author = result.metadata.get("author", "")
        org = result.metadata.get("organization", "")
        date = result.metadata.get("human_date", "")
        domain = result.metadata.get("source_domain", "")

        citation = f'"{result.title}"'
        if author or org or date:
            citation += " - "
            if author:
                citation += author
                if org:
                    citation += f" ({org})"
            elif org:
                citation += org

            if date and (author or org):
                citation += f", {date}"
            elif date:
                citation += date
        elif domain:
            citation += f" - {domain}"

        result.metadata["citation"] = citation
