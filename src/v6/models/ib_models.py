"""
Pydantic Models for IB Data Validation

This module provides Pydantic models for validating Interactive Brokers API responses.
Pydantic is used here (instead of dataclasses) because IB API data is external and can be malformed.
Field validation ensures data integrity before it enters the system.

Key patterns:
- Field constraints: ge/le for ranges, min_length for strings
- Custom validators: Strike range, expiry in future
- validate_assignment=True: Validates on every assignment, not just init
- json_encoders: Proper serialization for Decimal, date, datetime

Decision tree (from research):
    Does this data come from outside my process?
    ├─ Yes → Use Pydantic (validation critical) ← WE ARE HERE
    └─ No → Use dataclass (performance matters)
"""

from pydantic import BaseModel, Field, field_validator
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, Literal
from enum import Enum


class OptionRight(str, Enum):
    """Option type enum."""

    CALL = "C"
    PUT = "P"


class PositionStatus(str, Enum):
    """Position status enum."""

    OPEN = "open"
    CLOSED = "closed"
    ROLLING = "rolling"


class Greeks(BaseModel):
    """
    Options Greeks from IB API or calculated.

    Validates that all Greeks are within reasonable ranges (-1 to 1).
    IB API provides these via ticker.modelGreeks, but we validate to catch anomalies.

    Attributes:
        delta: Delta sensitivity (rate of price change relative to underlying)
        gamma: Gamma sensitivity (rate of delta change)
        theta: Theta time decay (rate of value loss over time)
        vega: Vega volatility sensitivity (rate of value change relative to IV)
    """

    delta: float = Field(ge=-1, le=1, description="Delta sensitivity")
    gamma: float = Field(ge=-1, le=1, description="Gamma sensitivity")
    theta: float = Field(ge=-1, le=1, description="Theta time decay")
    vega: float = Field(ge=-1, le=1, description="Vega volatility sensitivity")

    class Config:
        validate_assignment = True


class OptionLeg(BaseModel):
    """
    Pydantic model for option leg - validates IB data.

    This model represents a single option leg within a strategy (e.g., one side of an iron condor).
    Field validation ensures IB API data is sane before persisting to Delta Lake.

    Attributes:
        leg_id: Unique identifier for this leg
        strategy_id: ID of the parent strategy
        symbol: Underlying symbol (e.g., "SPY")
        strike: Strike price (must be between 1 and 10000)
        expiry: Expiration date (must be in future)
        right: Option type (CALL or PUT)
        quantity: Number of contracts (can be negative for short positions)
        open_price: Average entry price per share
        current_price: Current market price per share
        greeks: Current Greeks values
        status: Position status (open, closed, rolling)

    Raises:
        ValueError: If strike out of range, expiry in past, or other validation fails
    """

    leg_id: str = Field(..., min_length=1)
    strategy_id: str = Field(..., min_length=1)
    symbol: str = Field(..., min_length=1)
    strike: Decimal = Field(..., gt=0, description="Strike price")
    expiry: date = Field(..., description="Expiration date")
    right: OptionRight
    quantity: int = Field(..., ge=-1000, le=1000, description="Quantity (can be negative for short)")
    open_price: float = Field(..., ge=0, description="Average entry price")
    current_price: float = Field(..., ge=0, description="Current market price")
    greeks: Greeks
    status: PositionStatus

    @field_validator("strike")
    def validate_strike(cls, v):
        """
        Ensure strike is reasonable.

        IB API can return malformed data in edge cases. This validator catches anomalies
        like negative strikes or unreasonably high values (e.g., 1,000,000).

        Args:
            v: Strike price from IB API

        Returns:
            Validated strike price

        Raises:
            ValueError: If strike out of range (1-10000)
        """
        if v < 1 or v > 10000:
            raise ValueError("Strike price out of range (1-10000)")
        return v

    @field_validator("expiry")
    def validate_expiry(cls, v):
        """
        Ensure expiry is in future.

        Options cannot have expiry dates in the past. This catches IB API edge cases
        and data synchronization issues.

        Args:
            v: Expiration date from IB API

        Returns:
            Validated expiry date

        Raises:
            ValueError: If expiry is not in the future
        """
        if v <= date.today():
            raise ValueError("Expiry must be in the future")
        return v

    class Config:
        validate_assignment = True  # Validate on every assignment
        json_encoders = {
            Decimal: float,
            date: str,
            datetime: str,
        }


class StrategyPosition(BaseModel):
    """
    Pydantic model for strategy position.

    Represents a complete options strategy (e.g., iron condor, vertical spread) with all legs.
    Validates strategy_type against allowed values to prevent invalid strategies entering system.

    Attributes:
        strategy_id: Unique identifier for this strategy
        strategy_type: Type of strategy (iron_condor, vertical_spread, etc.)
        symbol: Underlying symbol
        status: Position status
        entry_date: When strategy was opened
        exit_date: When strategy was closed (None if still open)
        entry_price: Net credit/debit at entry
        exit_price: Net credit/debit at exit (None if still open)
        quantity: Number of contracts (usually 1 for multi-leg strategies)
        greeks: Aggregate Greeks across all legs
        unrealized_pnl: Current unrealized profit/loss
        realized_pnl: Realized profit/loss (after exit)

    Raises:
        ValueError: If strategy_type is not in allowed list
    """

    strategy_id: str = Field(..., min_length=1)
    strategy_type: str = Field(..., min_length=1)
    symbol: str = Field(..., min_length=1)
    status: PositionStatus
    entry_date: datetime
    exit_date: Optional[datetime] = None
    entry_price: float = Field(ge=0)
    exit_price: Optional[float] = None
    quantity: int
    greeks: Greeks
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0

    @field_validator("strategy_type")
    def validate_strategy_type(cls, v):
        """
        Validate strategy type.

        Ensures only supported strategy types enter the system. This prevents typos
        and unsupported strategies from causing issues downstream.

        Args:
            v: Strategy type string

        Returns:
            Validated strategy type

        Raises:
            ValueError: If strategy_type is not in allowed list
        """
        valid_types = ["iron_condor", "vertical_spread", "calendar_spread", "butterfly", "strangle"]
        if v not in valid_types:
            raise ValueError(f"Invalid strategy type: {v}. Must be one of {valid_types}")
        return v

    class Config:
        validate_assignment = True
        json_encoders = {
            datetime: str,
        }


class GreeksSnapshot(BaseModel):
    """
    Pydantic model for Greeks snapshots (for time-travel analytics).

    Stores portfolio Greeks at a point in time for analytics and backtesting.
    Delta Lake time-travel enables historical analysis of risk exposure.

    Attributes:
        strategy_id: Strategy identifier
        symbol: Underlying symbol
        greeks: Greeks values at this point in time
        portfolio_delta: Portfolio-level delta (sum of all positions)
        portfolio_gamma: Portfolio-level gamma
        portfolio_theta: Portfolio-level theta
        portfolio_vega: Portfolio-level vega
        timestamp: When this snapshot was taken
    """

    strategy_id: str
    symbol: str
    greeks: Greeks
    portfolio_delta: float
    portfolio_gamma: float
    portfolio_theta: float
    portfolio_vega: float
    timestamp: datetime


class Trade(BaseModel):
    """
    Pydantic model for trade execution.

    Records each trade execution (buy/sell/open/close) for audit trail and P&L calculation.

    Attributes:
        transaction_id: Unique identifier for this transaction
        strategy_id: Parent strategy identifier
        leg_id: Leg identifier (for multi-leg strategies)
        action: Trade action (BUY, SELL, OPEN, CLOSE)
        quantity: Number of contracts traded
        price: Execution price per share
        commission: Commission paid to broker
        timestamp: When trade was executed
    """

    transaction_id: str = Field(..., min_length=1)
    strategy_id: str = Field(..., min_length=1)
    leg_id: str = Field(..., min_length=1)
    action: Literal["BUY", "SELL", "OPEN", "CLOSE"]
    quantity: int
    price: float
    commission: float = 0.0
    timestamp: datetime
