"""Configuration management.

This module provides backward compatibility while using the new standardized
configuration loading patterns.
"""

from functools import lru_cache

from .config.settings import get_settings as _get_settings
from .models.config import Settings

# Re-export for backward compatibility
__all__ = ["get_settings", "Settings"]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Get application settings using standardized configuration loading.

    This function maintains backward compatibility while using the new
    streamlined configuration loading system internally.
    """
    return _get_settings()
