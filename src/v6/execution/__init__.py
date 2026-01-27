"""
Order Execution Package

Provides order execution engine for IB API with support for:
- Basic orders (market, limit, stop)
- Bracket orders (entry + take profit + stop loss)
- OCA groups (One-Cancels-All)
- Position management (close, roll)
- Dry run mode for testing

Usage:
    from src.v6.execution import OrderExecutionEngine, Order, BracketOrder, ExecutionResult
    from src.v6.utils import IBConnectionManager

    ib_conn = IBConnectionManager()
    engine = OrderExecutionEngine(ib_conn, dry_run=False)

    result = await engine.place_order(contract, order)
"""

from src.v6.execution.engine import OrderExecutionEngine
from src.v6.execution.models import (
    BracketOrder,
    ExecutionResult,
    Order,
    OrderAction,
    OrderStatus,
    OrderType,
    TimeInForce,
)

__all__ = [
    "OrderExecutionEngine",
    "Order",
    "OrderStatus",
    "OrderType",
    "OrderAction",
    "TimeInForce",
    "BracketOrder",
    "ExecutionResult",
]
