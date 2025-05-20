"""Metadata enrichment for search results.

This module provides functions to extract, normalize, and enhance
metadata for search results, including date parsing, source attribution,
and citation formatting.
"""

import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Union
from urllib.parse import urlparse

import dateparser

from ..models.results import SearchResult


def enrich_result_metadata(result: SearchResult) -> None:
    """
    Enrich a search result with additional metadata.

    This function extracts and normalizes metadata from the result's
    title, snippet, URL, and existing metadata.

    Args:
        result: The search result to enrich
    """
    # Extract and normalize date information
    extract_and_normalize_date(result)

    # Extract source domain and attribution
    extract_source_info(result)

    # Extract content metrics
    extract_content_metrics(result)

    # Create citation if possible
    generate_citation(result)


def extract_and_normalize_date(result: SearchResult) -> None:
    """
    Extract and normalize date information from a search result.

    Looks for dates in existing metadata, title, and snippet.
    Normalizes to ISO format and adds human-readable date.

    Args:
        result: The search result to process
    """
    # If already has normalized date, skip
    if "normalized_date" in result.metadata:
        return

    # Check if published_date already exists in metadata
    if "published_date" in result.metadata:
        date_str = result.metadata["published_date"]
    else:
        # Look for dates in title and snippet
        date_str = None
        date_candidates = []

        # Common date formats to look for
        date_patterns = [
            # Complete dates with month names
            r"\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{4}",
            r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4}",
            # ISO and similar formats (YYYY-MM-DD)
            r"\d{4}-\d{1,2}-\d{1,2}",
            # MM/DD/YYYY or DD/MM/YYYY
            r"\d{1,2}/\d{1,2}/\d{4}",
            # MM.DD.YYYY or DD.MM.YYYY
            r"\d{1,2}\.\d{1,2}\.\d{4}",
            # Relative dates ("2 days ago", "yesterday", etc.)
            r"(?:yesterday|today|(?:\d+\s+)?(?:days?|weeks?|months?|years?)\s+ago)",
        ]

        # Check title
        for pattern in date_patterns:
            matches = re.findall(pattern, result.title)
            date_candidates.extend(matches)

        # Check snippet
        for pattern in date_patterns:
            matches = re.findall(pattern, result.snippet)
            date_candidates.extend(matches)

        # Use first found date if any
        if date_candidates:
            date_str = date_candidates[0]

    # Parse the date if found
    if date_str:
        try:
            # Parse with dateparser which handles many formats including relative dates
            parsed_date = dateparser.parse(
                date_str, settings={"RETURN_AS_TIMEZONE_AWARE": True}
            )

            if parsed_date:
                # Store ISO format
                result.metadata["normalized_date"] = parsed_date.isoformat()

                # Store year, month, day separately for easier filtering
                result.metadata["year"] = parsed_date.year
                result.metadata["month"] = parsed_date.month
                result.metadata["day"] = parsed_date.day

                # Store human-readable format
                result.metadata["human_date"] = parsed_date.strftime("%B %d, %Y")

                # If no published_date was set, set it now
                if "published_date" not in result.metadata:
                    result.metadata["published_date"] = parsed_date.isoformat()

                # Add relative time description
                now = datetime.now(parsed_date.tzinfo)
                delta = now - parsed_date
                if delta.days == 0:
                    if delta.seconds < 3600:
                        mins = delta.seconds // 60
                        result.metadata["relative_time"] = (
                            f"{mins} minute{'s' if mins != 1 else ''} ago"
                        )
                    else:
                        hours = delta.seconds // 3600
                        result.metadata["relative_time"] = (
                            f"{hours} hour{'s' if hours != 1 else ''} ago"
                        )
                elif delta.days == 1:
                    result.metadata["relative_time"] = "Yesterday"
                elif delta.days < 7:
                    result.metadata["relative_time"] = f"{delta.days} days ago"
                elif delta.days < 30:
                    weeks = delta.days // 7
                    result.metadata["relative_time"] = (
                        f"{weeks} week{'s' if weeks != 1 else ''} ago"
                    )
                elif delta.days < 365:
                    months = delta.days // 30
                    result.metadata["relative_time"] = (
                        f"{months} month{'s' if months != 1 else ''} ago"
                    )
                else:
                    years = delta.days // 365
                    result.metadata["relative_time"] = (
                        f"{years} year{'s' if years != 1 else ''} ago"
                    )
        except Exception:
            # If parsing fails, don't add date metadata
            pass


def extract_source_info(result: SearchResult) -> None:
    """
    Extract and normalize source information from the URL.

    Extracts domain, organization name, and other attribution info.

    Args:
        result: The search result to process
    """
    # Extract domain if not already present
    if "source_domain" not in result.metadata:
        try:
            parsed_url = urlparse(result.url)
            domain = parsed_url.netloc.lower()
            # Remove www prefix if present
            domain = re.sub(r"^www\d?\.", "", domain)
            result.metadata["source_domain"] = domain

            # Try to extract organization name from domain
            org_name = None

            # Extract from common domain patterns
            domain_parts = domain.split(".")
            if len(domain_parts) >= 2:
                if domain_parts[-1] in ["com", "org", "net", "io"]:
                    # For commercial/organization domains, use the subdomain
                    org_name = domain_parts[-2]
                    # Convert kebab/snake case to title case
                    if "-" in org_name:
                        org_name = " ".join(
                            word.capitalize() for word in org_name.split("-")
                        )
                    elif "_" in org_name:
                        org_name = " ".join(
                            word.capitalize() for word in org_name.split("_")
                        )
                    else:
                        org_name = org_name.capitalize()

                elif domain_parts[-1] in ["edu", "gov"]:
                    # For educational or governmental domains
                    if len(domain_parts) > 2:
                        # Use full domain minus the TLD
                        org_name = ".".join(domain_parts[:-1])
                    else:
                        org_name = domain_parts[0]

            if org_name:
                result.metadata["organization"] = org_name

        except Exception:
            # If parsing fails, don't add domain metadata
            pass


def extract_content_metrics(result: SearchResult) -> None:
    """
    Extract metrics about the content quality and length.

    Estimates reading time, word count, and other useful metrics.

    Args:
        result: The search result to process
    """
    # Skip if metrics already extracted
    if "reading_time" in result.metadata:
        return

    # Calculate word count if raw content is available
    if result.raw_content:
        content = result.raw_content
    else:
        # Use snippet if raw content not available
        content = result.snippet

    # Count words
    word_count = len(re.findall(r"\b\w+\b", content))
    result.metadata["word_count"] = word_count

    # Estimate reading time (average reading speed: 200-250 words per minute)
    reading_time_minutes = max(1, round(word_count / 225))
    result.metadata["reading_time"] = reading_time_minutes

    if reading_time_minutes == 1:
        result.metadata["reading_time_display"] = "1 minute read"
    else:
        result.metadata["reading_time_display"] = f"{reading_time_minutes} minute read"

    # Try to detect if content has images
    if result.raw_content:
        # Look for image patterns in HTML or markdown
        image_patterns = [
            r"<img[^>]+src=",  # HTML img tag
            r"!\[.*?\]\(.*?\)",  # Markdown image
            r'src=["\'](https?://.*?)["\']',  # src attribute
        ]

        image_count = 0
        for pattern in image_patterns:
            matches = re.findall(pattern, result.raw_content)
            image_count += len(matches)

        if image_count > 0:
            result.metadata["image_count"] = image_count


def generate_citation(result: SearchResult) -> None:
    """
    Generate a citation for the search result.

    Creates both academic and casual citation formats if enough
    information is available.

    Args:
        result: The search result to process
    """
    # Skip if citation already generated
    if "citation" in result.metadata:
        return

    # Check if we have enough information for a citation
    has_title = bool(result.title)
    has_date = (
        "normalized_date" in result.metadata or "published_date" in result.metadata
    )
    has_domain = "source_domain" in result.metadata
    has_org = "organization" in result.metadata

    # Need at least title and one of (date, domain, org)
    if has_title and (has_date or has_domain or has_org):
        # Get organization/author
        author = result.metadata.get("author")
        org = result.metadata.get("organization")
        domain = result.metadata.get("source_domain", "")

        # Get formatted date
        if "human_date" in result.metadata:
            date = result.metadata["human_date"]
        elif "published_date" in result.metadata:
            try:
                date_str = result.metadata["published_date"]
                parsed_date = dateparser.parse(date_str)
                if parsed_date:
                    date = parsed_date.strftime("%B %d, %Y")
                else:
                    date = date_str
            except:
                date = result.metadata["published_date"]
        else:
            date = ""

        # Create citation based on available information
        citation_parts = []

        # For casual citation
        casual_citation = ""
        if author:
            casual_citation += f"{author}"
            if org:
                casual_citation += f" ({org})"
        elif org:
            casual_citation += f"{org}"

        if date and (author or org):
            casual_citation += f", {date}"
        elif date:
            casual_citation += f"{date}"

        if casual_citation:
            casual_citation = f'"{result.title}" - {casual_citation}'
        elif domain:
            casual_citation = f'"{result.title}" - {domain}'
        else:
            casual_citation = f'"{result.title}"'

        result.metadata["citation"] = casual_citation

        # For academic citation (Chicago style)
        if author:
            citation_parts.append(f"{author}.")
        elif org:
            citation_parts.append(f"{org}.")

        if result.title:
            citation_parts.append(f'"{result.title}."')

        if domain:
            citation_parts.append(domain)

        if date:
            citation_parts.append(f"({date}).")

        if result.url:
            citation_parts.append(result.url)

        if citation_parts:
            result.metadata["academic_citation"] = " ".join(citation_parts)
