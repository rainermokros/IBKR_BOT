"""
Smart Strike Selector - Quicksort-Style Algorithm

Efficient strike selection using directional search instead of brute force.
"""

from dataclasses import dataclass
from typing import List, Optional, Tuple
from loguru import logger
import math


@dataclass(slots=True)
class SmartStrikeSelector:
    """Smart strike selector using Quicksort-style directional search."""

    iv: Optional[float] = None
    hv: Optional[float] = None
    days_to_expiration: int = 45
    strike_interval: float = 1.0
    tolerance: float = 0.03

    def calculate_std_deviation(self, underlying_price: float) -> float:
        """Calculate 1 standard deviation for the underlying."""
        vol = self.iv if self.iv is not None else self.hv
        if vol is None:
            vol = 0.20
            logger.warning("No IV/HV data, using default 20% volatility")

        trading_days = self.days_to_expiration
        std_dev = underlying_price * vol * math.sqrt(trading_days / 365)
        return std_dev

    def estimate_strike_interval(self, underlying_price: float) -> float:
        """Estimate strike price interval from underlying price."""
        if underlying_price < 50:
            interval = 1.0
        elif underlying_price < 100:
            interval = 2.5
        elif underlying_price < 500:
            interval = 5.0
        else:
            interval = 10.0
        return interval

    def find_strike_with_delta_binary_search(
        self,
        symbol: str,
        right: str,
        target_delta: float,
        underlying_price: float,
        get_delta_func: callable,
        max_iterations: int = 10
    ) -> Tuple[float, float]:
        """
        Find strike with target delta using binary search.
        """
        logger.info(f"Binary search for {right} strike with delta ≈ {target_delta:.2f}")

        std_dev = self.calculate_std_deviation(underlying_price)
        self.strike_interval = self.estimate_strike_interval(underlying_price)

        # Start at ATM ± 1 STD
        if right.upper() == 'PUT':
            pivot_strike = self._round_to_interval(underlying_price - std_dev)
        else:
            pivot_strike = self._round_to_interval(underlying_price + std_dev)

        logger.info(f"Initial pivot: ${pivot_strike:.0f} (ATM ± 1 STD)")

        best_strike = pivot_strike
        best_delta = None
        best_error = float('inf')

        iteration = 0
        prev_strike = None

        while iteration < max_iterations:
            iteration += 1

            # Avoid infinite loops
            if pivot_strike == prev_strike:
                logger.warning(f"Strike ${pivot_strike:.0f} repeated, terminating search")
                break

            try:
                pivot_delta = get_delta_func(pivot_strike, right)
                delta_abs = abs(pivot_delta)
            except Exception as e:
                logger.warning(f"Failed to get delta for ${pivot_strike:.0f}: {e}")
                # Move in the direction that increases our chance of finding data
                pivot_strike += self.strike_interval
                continue

            logger.info(f"Iteration {iteration}: Strike ${pivot_strike:.0f}, Delta={delta_abs:.3f}, Target={target_delta:.2f}")

            # Check if within tolerance
            error = abs(delta_abs - target_delta)
            if error < best_error:
                best_error = error
                best_strike = pivot_strike
                best_delta = pivot_delta

            if error <= self.tolerance:
                logger.info(f"✓ Found strike ${pivot_strike:.0f} with delta {delta_abs:.3f}")
                return pivot_strike, pivot_delta

            # Determine search direction
            prev_strike = pivot_strike

            if right.upper() == 'PUT':
                # Puts: Negative delta
                # If |delta| > target: Too OTM, move closer to ATM (higher strike)
                # If |delta| < target: Too close to ATM, move further OTM (lower strike)
                
                if delta_abs > target_delta:
                    # Too OTM, move closer to ATM (higher strike)
                    pivot_strike = self._round_to_interval(pivot_strike + self.strike_interval)
                else:
                    # Too close to ATM, move further OTM (lower strike)
                    pivot_strike = self._round_to_interval(pivot_strike - self.strike_interval)

            else:  # CALL
                # Calls: Positive delta
                # If delta > target: Too OTM, move closer to ATM (lower strike)
                # If delta < target: Too close to ATM, move further OTM (higher strike)
                
                if pivot_delta > target_delta:
                    # Too OTM, move closer to ATM (lower strike)
                    pivot_strike = self._round_to_interval(pivot_strike - self.strike_interval)
                else:
                    # Too close to ATM, move further OTM (higher strike)
                    pivot_strike = self._round_to_interval(pivot_strike + self.strike_interval)

        # Return best found
        if best_delta is not None:
            logger.warning(f"Max iterations reached, returning best strike: ${best_strike:.0f}")
            return best_strike, best_delta
        else:
            raise ValueError(f"Could not find {right} strike after {max_iterations} iterations")

    def _round_to_interval(self, price: float) -> float:
        """Round price to nearest strike interval."""
        interval = self.strike_interval if self.strike_interval else 1.0
        return round(price / interval) * interval
