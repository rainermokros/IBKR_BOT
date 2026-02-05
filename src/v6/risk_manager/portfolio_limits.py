"""
Portfolio Limits Checker

This module provides the PortfolioLimitsChecker class that validates
portfolio-level risk limits before allowing new position entries.

Key features:
- Portfolio delta and gamma limit checking
- Per-symbol delta limit checking
- Concentration limit checking (position value / total exposure)
- Portfolio health monitoring
- Remaining capacity calculation

Usage:
    >>> from v6.risk import RiskLimitsConfig
    >>> from v6.risk_manager.portfolio_limits import PortfolioLimitsChecker
    >>>
    >>> limits = RiskLimitsConfig(max_portfolio_delta=50.0)
    >>> checker = PortfolioLimitsChecker(risk_calculator, limits)
    >>>
    >>> allowed, reason = await checker.check_entry_allowed(
    ...     new_position_delta=5.0,
    ...     symbol="SPY",
    ...     position_value=10000.0
    ... )
"""

from loguru import logger

from v6.strategy_builder.decision_engine.portfolio_risk import PortfolioRiskCalculator
from v6.risk_manager.models import RiskLimitsConfig


class PortfolioLimitsChecker:
    """
    Checks portfolio-level risk limits before allowing position entries.

    Validates that new positions would not exceed configured risk thresholds
    including portfolio delta, per-symbol delta, and concentration limits.

    Attributes:
        risk_calc: PortfolioRiskCalculator for computing current portfolio risk
        limits: RiskLimitsConfig with configured thresholds

    Example:
        >>> limits = RiskLimitsConfig(max_portfolio_delta=50.0)
        >>> checker = PortfolioLimitsCalculator(risk_calculator, limits)
        >>>
        >>> allowed, reason = await checker.check_entry_allowed(
        ...     new_position_delta=5.0,
        ...     symbol="SPY",
        ...     position_value=10000.0
        ... )
        >>> if not allowed:
        ...     print(f"Entry rejected: {reason}")
    """

    def __init__(
        self,
        risk_calculator: PortfolioRiskCalculator,
        limits: RiskLimitsConfig,
    ):
        """
        Initialize portfolio limits checker.

        Args:
            risk_calculator: PortfolioRiskCalculator for computing portfolio risk
            limits: RiskLimitsConfig with risk thresholds
        """
        self.risk_calc = risk_calculator
        self.limits = limits
        self.logger = logger.bind(component="PortfolioLimitsChecker")

    async def check_entry_allowed(
        self,
        new_position_delta: float,
        symbol: str,
        position_value: float,
    ) -> tuple[bool, str | None]:
        """
        Check if new position would exceed portfolio limits.

        Evaluates all portfolio-level risk limits and returns whether
        the entry is allowed along with a rejection reason if not allowed.

        Args:
            new_position_delta: Delta contribution of new position
            symbol: Underlying symbol for the position
            position_value: Notional value of the position

        Returns:
            Tuple of (allowed, rejection_reason):
            - allowed: True if entry is allowed, False otherwise
            - rejection_reason: Human-readable reason if not allowed, None if allowed

        Example:
            >>> allowed, reason = await checker.check_entry_allowed(
            ...     new_position_delta=5.0,
            ...     symbol="SPY",
            ...     position_value=10000.0
            ... )
            >>> if not allowed:
            ...     print(f"Entry rejected: {reason}")
        """
        # Get current portfolio risk
        risk = await self.risk_calc.calculate_portfolio_risk()

        # Check 1: Portfolio delta limit
        new_portfolio_delta = risk.greeks.delta + new_position_delta
        if abs(new_portfolio_delta) > self.limits.max_portfolio_delta:
            reason = (
                f"Portfolio delta would exceed limit: "
                f"{new_portfolio_delta:.2f} > {self.limits.max_portfolio_delta:.2f}"
            )
            self.logger.warning(
                f"Entry REJECTED: {reason} "
                f"(current={risk.greeks.delta:.2f}, new={new_position_delta:.2f})"
            )
            return False, reason

        # Check 2: Portfolio gamma limit
        # Note: We need to estimate gamma contribution
        # For now, check if current gamma already exceeds limit
        if abs(risk.greeks.gamma) > self.limits.max_portfolio_gamma:
            reason = (
                f"Portfolio gamma already exceeds limit: "
                f"{risk.greeks.gamma:.2f} > {self.limits.max_portfolio_gamma:.2f}"
            )
            self.logger.warning(f"Entry REJECTED: {reason}")
            return False, reason

        # Check 3: Per-symbol delta limit
        symbol_delta = risk.greeks.delta_per_symbol.get(symbol, 0.0)
        new_symbol_delta = symbol_delta + new_position_delta
        if abs(new_symbol_delta) > self.limits.max_per_symbol_delta:
            reason = (
                f"Symbol {symbol} delta would exceed limit: "
                f"{new_symbol_delta:.2f} > {self.limits.max_per_symbol_delta:.2f}"
            )
            self.logger.warning(
                f"Entry REJECTED: {reason} "
                f"(current={symbol_delta:.2f}, new={new_position_delta:.2f})"
            )
            return False, reason

        # Check 4: Concentration limit (position value / total exposure)
        new_total_exposure = risk.exposure.total_exposure + position_value
        if new_total_exposure > 0:
            position_concentration = position_value / new_total_exposure
            if position_concentration > self.limits.max_single_position_pct:
                reason = (
                    f"Position would exceed concentration limit: "
                    f"{position_concentration:.1%} > {self.limits.max_single_position_pct:.1%}"
                )
                self.logger.warning(
                    f"Entry REJECTED: {reason} "
                    f"(position=${position_value:,.0f}, total=${new_total_exposure:,.0f})"
                )
                return False, reason

        # Check 5: Correlated exposure limit (by symbol)
        # Calculate new symbol exposure
        current_symbol_exposure = 0.0
        try:
            # Get current exposure for this symbol
            symbol_exposure_pct = risk.exposure.correlated_exposure.get(symbol, 0.0)
            current_symbol_exposure = symbol_exposure_pct * risk.exposure.total_exposure
        except Exception:
            # If we can't calculate, be conservative
            current_symbol_exposure = 0.0

        new_symbol_exposure = current_symbol_exposure + position_value
        if new_total_exposure > 0:
            new_symbol_exposure_pct = new_symbol_exposure / new_total_exposure
            if new_symbol_exposure_pct > self.limits.max_correlated_pct:
                reason = (
                    f"Symbol {symbol} exposure would exceed limit: "
                    f"{new_symbol_exposure_pct:.1%} > {self.limits.max_correlated_pct:.1%}"
                )
                self.logger.warning(
                    f"Entry REJECTED: {reason} "
                    f"(symbol_exposure=${new_symbol_exposure:,.0f}, "
                    f"total=${new_total_exposure:,.0f})"
                )
                return False, reason

        # Check 6: Total exposure cap (if configured)
        if self.limits.total_exposure_cap is not None:
            if new_total_exposure > self.limits.total_exposure_cap:
                reason = (
                    f"Total exposure would exceed cap: "
                    f"${new_total_exposure:,.0f} > ${self.limits.total_exposure_cap:,.0f}"
                )
                self.logger.warning(f"Entry REJECTED: {reason}")
                return False, reason

        # All checks passed
        self.logger.info(
            f"Entry ALLOWED by portfolio limits: "
            f"delta={new_portfolio_delta:.2f}/{self.limits.max_portfolio_delta:.2f}, "
            f"symbol={symbol}, "
            f"exposure=${new_total_exposure:,.0f}"
        )
        return True, None

    async def check_portfolio_health(self) -> list[str]:
        """
        Check current portfolio against all limits.

        Returns a list of warning messages for any limits that are
        currently exceeded, even without new positions.

        Returns:
            List of warning messages (empty if portfolio is healthy)

        Example:
            >>> warnings = await checker.check_portfolio_health()
            >>> if warnings:
            ...     for warning in warnings:
            ...         print(f"WARNING: {warning}")
        """
        warnings = []

        # Get current portfolio risk
        risk = await self.risk_calc.calculate_portfolio_risk()

        # Check portfolio delta
        if abs(risk.greeks.delta) > self.limits.max_portfolio_delta:
            warnings.append(
                f"Portfolio delta exceeds limit: "
                f"{risk.greeks.delta:.2f} > {self.limits.max_portfolio_delta:.2f}"
            )

        # Check portfolio gamma
        if abs(risk.greeks.gamma) > self.limits.max_portfolio_gamma:
            warnings.append(
                f"Portfolio gamma exceeds limit: "
                f"{risk.greeks.gamma:.2f} > {self.limits.max_portfolio_gamma:.2f}"
            )

        # Check per-symbol deltas
        for symbol, delta in risk.greeks.delta_per_symbol.items():
            if abs(delta) > self.limits.max_per_symbol_delta:
                warnings.append(
                    f"Symbol {symbol} delta exceeds limit: "
                    f"{delta:.2f} > {self.limits.max_per_symbol_delta:.2f}"
                )

        # Check concentration
        if risk.exposure.max_single_position > self.limits.max_single_position_pct:
            warnings.append(
                f"Max position concentration exceeds limit: "
                f"{risk.exposure.max_single_position:.1%} > "
                f"{self.limits.max_single_position_pct:.1%}"
            )

        # Check correlated exposure
        for symbol, exposure_pct in risk.exposure.correlated_exposure.items():
            if exposure_pct > self.limits.max_correlated_pct:
                warnings.append(
                    f"Symbol {symbol} exposure exceeds limit: "
                    f"{exposure_pct:.1%} > {self.limits.max_correlated_pct:.1%}"
                )

        # Check total exposure cap
        if (
            self.limits.total_exposure_cap is not None
            and risk.exposure.total_exposure > self.limits.total_exposure_cap
        ):
            warnings.append(
                f"Total exposure exceeds cap: "
                f"${risk.exposure.total_exposure:,.0f} > "
                f"${self.limits.total_exposure_cap:,.0f}"
            )

        if warnings:
            self.logger.warning(f"Portfolio health check found {len(warnings)} issues")
        else:
            self.logger.info("Portfolio health check passed")

        return warnings

    async def get_remaining_capacity(
        self,
        symbol: str,
    ) -> dict[str, float]:
        """
        Calculate remaining capacity for new entries by symbol.

        Returns the remaining capacity across different risk dimensions
        before limits would be exceeded.

        Args:
            symbol: Symbol to calculate capacity for

        Returns:
            Dictionary with remaining capacity:
            - delta: Remaining delta capacity before hitting limit
            - exposure: Remaining exposure capacity in dollars
            - position_count: Number of positions that can still be added
            - symbol_delta: Remaining delta capacity for this specific symbol

        Example:
            >>> capacity = await checker.get_remaining_capacity("SPY")
            >>> print(f"Remaining delta capacity: {capacity['delta']:.2f}")
            >>> print(f"Remaining exposure: ${capacity['exposure']:,.0f}")
        """
        # Get current portfolio risk
        risk = await self.risk_calc.calculate_portfolio_risk()

        # Calculate remaining delta capacity
        remaining_delta = self.limits.max_portfolio_delta - abs(risk.greeks.delta)

        # Calculate remaining symbol delta capacity
        symbol_delta = risk.greeks.delta_per_symbol.get(symbol, 0.0)
        remaining_symbol_delta = self.limits.max_per_symbol_delta - abs(symbol_delta)

        # Calculate remaining exposure capacity
        # This is the smaller of:
        # 1. Total exposure cap (if set)
        # 2. Concentration limit (max_single_position_pct)
        remaining_exposure = float("inf")

        if self.limits.total_exposure_cap is not None:
            remaining_exposure = min(
                remaining_exposure,
                self.limits.total_exposure_cap - risk.exposure.total_exposure,
            )

        # Calculate based on concentration limit
        # Max single position = max_single_position_pct * total_exposure
        max_single_position = self.limits.max_single_position_pct * (
            risk.exposure.total_exposure + 1.0
        )  # Avoid division by zero
        remaining_exposure = min(remaining_exposure, max_single_position)

        # Position count capacity (not tracked by PortfolioRiskCalculator)
        # Return as placeholder
        remaining_position_count = float("inf")

        capacity = {
            "delta": max(0.0, remaining_delta),
            "symbol_delta": max(0.0, remaining_symbol_delta),
            "exposure": max(0.0, remaining_exposure),
            "position_count": remaining_position_count,
        }

        self.logger.debug(
            f"Remaining capacity for {symbol}: "
            f"delta={capacity['delta']:.2f}, "
            f"symbol_delta={capacity['symbol_delta']:.2f}, "
            f"exposure=${capacity['exposure']:,.0f}"
        )

        return capacity
