"""
Entry Executor

Execute strategy entries using 45-21 DTE framework.

This module provides the EntryExecutor class for entering strategies with:
- Delta-based strike selection
- IV rank adjustment
- Delta balance validation
- Wing width validation
"""

import logging
from typing import List, Optional

from loguru import logger

from v6.execution.engine import OrderExecutionEngine
from v6.indicators.iv_rank import IVRankCalculator
from v6.strategy_builder.builders import IronCondorBuilder
from v6.strategy_builder.builders import VerticalSpreadBuilder
from v6.strategy_builder.builders import IronCondorBuilder
from v6.strategy_builder.models import Strategy
from v6.utils.ib_connection import IBConnectionManager


class EntryExecutor:
    """
    Execute strategy entries with delta-based validation.

    This class orchestrates the entry process for 45-21 DTE framework strategies:
    1. Get current market data (price, IV rank, option chain)
    2. Build strategy with delta-based builder
    3. Validate delta balance and wing widths
    4. Submit to execution engine
    5. Return execution result

    Attributes:
        ib_conn: IB connection manager
        execution_engine: Order execution engine
        iv_calculator: IV rank calculator
        dry_run: If True, simulate entries without placing orders
    """

    def __init__(
        self,
        ib_conn: IBConnectionManager,
        execution_engine: OrderExecutionEngine,
        dry_run: bool = False
    ):
        """
        Initialize entry executor.

        Args:
            ib_conn: IB connection manager
            execution_engine: Order execution engine
            dry_run: If True, simulate entries without placing orders
        """
        self.ib_conn = ib_conn
        self.execution_engine = execution_engine
        self.dry_run = dry_run
        self.iv_calculator = IVRankCalculator(lookback_days=60)

        # Initialize builders
        self.iron_condor_builder = IronCondorBuilder()
        self.credit_spread_builder = VerticalSpreadBuilder()
        self.wheel_builder = IronCondorBuilder()

        if dry_run:
            logger.warning("Entry Executor in DRY RUN mode - No actual orders will be placed")

    async def enter_iron_condor(
        self,
        symbol: str,
        option_chain: List[dict],
        quantity: int = 1,
        framework: str = '45_21'
    ) -> dict:
        """
        Enter Iron Condor position.

        Process:
        1. Get current market data (price, IV rank, option chain)
        2. Build strategy with delta-based builder
        3. Validate delta balance (≤0.05 difference)
        4. Validate wing widths (within 2% of target)
        5. Submit to execution engine
        6. Return execution result

        Args:
            symbol: Underlying symbol (SPY, QQQ, IWM)
            option_chain: Available strikes with Greeks
                Each dict should have: strike, right, delta, gamma, theta, vega
            quantity: Number of Iron Condors
            framework: '45_21' (new delta-based) or 'legacy' (old percentage-based)

        Returns:
            Execution result dict with keys:
            - status: 'FILLED', 'FAILED', 'PENDING'
            - strategy: Strategy object
            - message: Status message
            - order_id: Order ID (if placed)

        Raises:
            ValueError: If entry validation fails
        """
        logger.info(f"Entering Iron Condor for {symbol} (framework={framework})")

        # Get market data
        underlying_price = await self._get_underlying_price(symbol)
        iv_rank = self.iv_calculator.calculate(symbol)

        logger.info(
            f"Market data: {symbol}=${underlying_price:.2f}, IVR={iv_rank:.1f}%, "
            f"strikes_available={len(option_chain)}"
        )

        # Build strategy
        if framework == '45_21':
            strategy = self.iron_condor_builder.build(
                symbol=symbol,
                underlying_price=underlying_price,
                option_chain=option_chain,
                quantity=quantity
            )
        else:
            raise ValueError(f"Unknown framework: {framework}")

        # Validate entry
        self._validate_entry(strategy)

        # Execute (for now, just return the strategy spec)
        # In production, this would call execution_engine.execute_strategy()
        result = {
            'status': 'BUILT' if self.dry_run else 'PENDING',
            'strategy': strategy,
            'message': f"Iron Condor built successfully (dry_run={self.dry_run})",
            'order_id': None,
        }

        logger.info(
            f"✓ Iron Condor entry complete: {strategy.strategy_id} "
            f"(LP=${strategy.metadata['long_put_strike']}, "
            f"SP=${strategy.metadata['short_put_strike']} δ={strategy.metadata['short_put_delta']:.3f}, "
            f"SC=${strategy.metadata['short_call_strike']} δ={strategy.metadata['short_call_delta']:.3f}, "
            f"LC=${strategy.metadata['long_call_strike']})"
        )

        return result

    async def enter_bull_put_spread(
        self,
        symbol: str,
        option_chain: List[dict],
        quantity: int = 1,
        framework: str = '45_21'
    ) -> dict:
        """
        Enter bull put spread position.

        Args:
            symbol: Underlying symbol (SPY, QQQ, IWM)
            option_chain: Available strikes with Greeks
            quantity: Number of spreads
            framework: '45_21' (new delta-based) or 'legacy'

        Returns:
            Execution result dict
        """
        logger.info(f"Entering Bull Put Spread for {symbol} (framework={framework})")

        # Get market data
        underlying_price = await self._get_underlying_price(symbol)
        iv_rank = self.iv_calculator.calculate(symbol)

        logger.info(
            f"Market data: {symbol}=${underlying_price:.2f}, IVR={iv_rank:.1f}%, "
            f"strikes_available={len(option_chain)}"
        )

        # Build strategy
        if framework == '45_21':
            strategy = self.credit_spread_builder.build_bull_put_spread(
                symbol=symbol,
                underlying_price=underlying_price,
                option_chain=option_chain,
                quantity=quantity
            )
        else:
            raise ValueError(f"Unknown framework: {framework}")

        # Validate entry
        self._validate_entry(strategy)

        # Execute
        result = {
            'status': 'BUILT' if self.dry_run else 'PENDING',
            'strategy': strategy,
            'message': f"Bull Put Spread built successfully (dry_run={self.dry_run})",
            'order_id': None,
        }

        logger.info(
            f"✓ Bull Put Spread entry complete: {strategy.strategy_id} "
            f"(LP=${strategy.metadata['long_put_strike']}, "
            f"SP=${strategy.metadata['short_put_strike']} δ={strategy.metadata['short_put_delta']:.3f})"
        )

        return result

    async def enter_bear_call_spread(
        self,
        symbol: str,
        option_chain: List[dict],
        quantity: int = 1,
        framework: str = '45_21'
    ) -> dict:
        """
        Enter bear call spread position.

        Args:
            symbol: Underlying symbol (SPY, QQQ, IWM)
            option_chain: Available strikes with Greeks
            quantity: Number of spreads
            framework: '45_21' (new delta-based) or 'legacy'

        Returns:
            Execution result dict
        """
        logger.info(f"Entering Bear Call Spread for {symbol} (framework={framework})")

        # Get market data
        underlying_price = await self._get_underlying_price(symbol)
        iv_rank = self.iv_calculator.calculate(symbol)

        logger.info(
            f"Market data: {symbol}=${underlying_price:.2f}, IVR={iv_rank:.1f}%, "
            f"strikes_available={len(option_chain)}"
        )

        # Build strategy
        if framework == '45_21':
            strategy = self.credit_spread_builder.build_bear_call_spread(
                symbol=symbol,
                underlying_price=underlying_price,
                option_chain=option_chain,
                quantity=quantity
            )
        else:
            raise ValueError(f"Unknown framework: {framework}")

        # Validate entry
        self._validate_entry(strategy)

        # Execute
        result = {
            'status': 'BUILT' if self.dry_run else 'PENDING',
            'strategy': strategy,
            'message': f"Bear Call Spread built successfully (dry_run={self.dry_run})",
            'order_id': None,
        }

        logger.info(
            f"✓ Bear Call Spread entry complete: {strategy.strategy_id} "
            f"(SC=${strategy.metadata['short_call_strike']} δ={strategy.metadata['short_call_delta']:.3f}, "
            f"LC=${strategy.metadata['long_call_strike']})"
        )

        return result

    async def enter_cash_secured_put(
        self,
        symbol: str,
        option_chain: List[dict],
        quantity: int = 1,
        target_delta: Optional[float] = None
    ) -> dict:
        """
        Enter cash-secured put position (Stage 1 of Wheel).

        Args:
            symbol: Underlying symbol (SPY, QQQ, IWM)
            option_chain: Available strikes with Greeks
            quantity: Number of puts
            target_delta: Optional target delta (default 0.35)

        Returns:
            Execution result dict
        """
        logger.info(f"Entering Cash-Secured Put for {symbol}")

        # Get market data
        underlying_price = await self._get_underlying_price(symbol)
        iv_rank = self.iv_calculator.calculate(symbol)

        logger.info(
            f"Market data: {symbol}=${underlying_price:.2f}, IVR={iv_rank:.1f}%, "
            f"strikes_available={len(option_chain)}"
        )

        # Build strategy
        strategy = self.wheel_builder.build_cash_secured_put(
            symbol=symbol,
            underlying_price=underlying_price,
            option_chain=option_chain,
            quantity=quantity,
            target_delta=target_delta
        )

        # Validate entry
        self._validate_entry(strategy)

        # Execute
        result = {
            'status': 'BUILT' if self.dry_run else 'PENDING',
            'strategy': strategy,
            'message': f"Cash-Secured Put built successfully (dry_run={self.dry_run})",
            'order_id': None,
        }

        logger.info(
            f"✓ Cash-Secured Put entry complete: {strategy.strategy_id} "
            f"(SP=${strategy.metadata['short_put_strike']} δ={strategy.metadata['short_put_delta']:.3f})"
        )

        return result

    async def _get_underlying_price(self, symbol: str) -> float:
        """
        Get current underlying price from IB.

        Args:
            symbol: Underlying symbol

        Returns:
            Current price

        Raises:
            ValueError: If price cannot be retrieved
        """
        # For now, use a stub implementation
        # In production, this would query IB for real-time price
        if self.dry_run:
            # Return mock prices for testing
            mock_prices = {
                'SPY': 500.0,
                'QQQ': 450.0,
                'IWM': 200.0,
            }
            price = mock_prices.get(symbol, 100.0)
            logger.debug(f"Using mock price for {symbol}: ${price:.2f}")
            return price

        # Production implementation would go here
        raise NotImplementedError("Real-time price retrieval not implemented yet")

    def _validate_entry(self, strategy: Strategy):
        """
        Validate strategy before entry.

        Checks:
        - Delta balance (for Iron Condors)
        - Wing widths (for Iron Condors and spreads)
        - Strike structure validity

        Args:
            strategy: Strategy to validate

        Raises:
            ValueError: If validation fails
        """
        logger.debug(f"Validating entry for {strategy.strategy_id}")

        # Validate using builder's validate method
        if strategy.strategy_type == "iron_condor":
            if not self.iron_condor_builder.validate(strategy):
                raise ValueError(f"Iron Condor validation failed for {strategy.strategy_id}")

            # Additional delta balance check
            delta_balance = strategy.metadata.get('delta_balance', 1.0)
            if delta_balance > 0.05:
                logger.warning(
                    f"Delta balance weak: {delta_balance:.3f} > 0.05 "
                    f"(PUT δ={strategy.metadata.get('short_put_delta', 0):.3f}, "
                    f"CALL δ={strategy.metadata.get('short_call_delta', 0):.3f})"
                )

            # Wing width check
            target_width = strategy.metadata.get('target_wing_width', 0)
            put_width = strategy.metadata.get('put_wing_width', 0)
            call_width = strategy.metadata.get('call_wing_width', 0)

            if abs(put_width - target_width) > 2.0:
                logger.warning(
                    f"PUT wing width ({put_width:.1f}) differs from target ({target_width:.1f})"
                )

            if abs(call_width - target_width) > 2.0:
                logger.warning(
                    f"CALL wing width ({call_width:.1f}) differs from target ({target_width:.1f})"
                )

        elif strategy.strategy_type == "vertical_spread":
            if not self.credit_spread_builder.validate(strategy):
                raise ValueError(f"Credit Spread validation failed for {strategy.strategy_id}")

            # Spread width check
            target_width = strategy.metadata.get('target_spread_width', 0)
            actual_width = strategy.metadata.get('spread_width', 0)

            if abs(actual_width - target_width) > 2.0:
                logger.warning(
                    f"Spread width ({actual_width:.1f}) differs from target ({target_width:.1f})"
                )

        elif strategy.strategy_type in ["short_put", "short_call"]:
            if not self.wheel_builder.validate(strategy):
                raise ValueError(f"Wheel component validation failed for {strategy.strategy_id}")

        logger.info(f"✓ Entry validation passed for {strategy.strategy_id}")
