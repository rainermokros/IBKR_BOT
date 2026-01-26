"""
Data repositories for Delta Lake operations.

This package provides repository classes for accessing Delta Lake tables
with a clean, encapsulated API.

Example:
    >>> from v6.data.repositories import PositionsRepository
    >>> repo = PositionsRepository()
    >>> positions = repo.get_latest()
    >>> open_positions = repo.get_open_positions()
"""

from .positions import PositionsRepository

__all__ = ["PositionsRepository"]
