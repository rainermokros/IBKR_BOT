"""
Data models for V6 trading system.

This module contains dataclass definitions shared across multiple components
to avoid circular imports.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class OptionContract:
    """
    Option contract data snapshot.

    Attributes:
        symbol: Underlying symbol (SPY, QQQ, IWM)
        timestamp: Snapshot timestamp
        strike: Strike price
        expiry: Expiration date (YYYYMMDD format)
        right: Put or Call ('P' or 'C')
        bid: Best bid price
        ask: Best ask price
        last: Last trade price
        volume: Trading volume
        open_interest: Open interest
        iv: Implied volatility
        delta: Option delta
        gamma: Option gamma
        theta: Option theta
        vega: Option vega
    """
    symbol: str
    timestamp: datetime
    strike: float
    expiry: str
    right: str
    bid: float
    ask: float
    last: float
    volume: int
    open_interest: Optional[int] = None
    iv: Optional[float] = None
    delta: Optional[float] = None
    gamma: Optional[float] = None
    theta: Optional[float] = None
    vega: Optional[float] = None
