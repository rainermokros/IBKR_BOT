#!/usr/bin/env python3
"""
Test: What Strategies Would Be Selected Today?

This script simulates the decision engine with realistic market scenarios
to show what strategies would be selected and WHY.

Usage: python test_strategy_selection_today.py
"""

import asyncio
from datetime import datetime

# Mock the decision engine with simplified logic for demonstration
class StrategySelector:
    """Simplified strategy selector based on V6 decision rules."""

    STRATEGY_MATRIX = """
    Market Outlook    | High IV (>50)              | Low IV (<50)
    -----------------|----------------------------|---------------------------
    Bullish          | Long Call (Debit)         | Bull Put Spread (Credit)
                     | Bull Call Spread (Debit)   | Cash-Secured Put (Credit)
                     | Call Backspread (Debit)    |
    Bearish          | Long Put (Debit)           | Bear Call Spread (Credit)
                     | Bear Put Spread (Debit)    |
    Neutral/Sideways | Short Straddle (Credit)    | Iron Condor (Credit)
                     | Short Strangle (Credit)    | Long Butterfly (Debit)
    """

    def __init__(self):
        print("\n" + "=" * 80)
        print("V6 TRADING BOT - STRATEGY SELECTION SIMULATION")
        print("=" * 80)
        print("\nStrategy Selection Matrix:")
        print(self.STRATEGY_MATRIX)

    def classify_market_outlook(self, price_change_1d, ma5, ma20):
        """
        Classify market outlook based on price action.

        Args:
            price_change_1d: 1-day price change (%)
            ma5: 5-day moving average
            ma20: 20-day moving average

        Returns:
            "bullish", "bearish", or "neutral"
        """
        # Price momentum
        if price_change_1d > 1.0:
            price_signal = "bullish"
        elif price_change_1d < -1.0:
            price_signal = "bearish"
        else:
            price_signal = "neutral"

        # Moving average relationship
        if ma5 > ma20 * 1.01:  # 5-day MA > 20-day MA by 1%
            ma_signal = "bullish"
        elif ma5 < ma20 * 0.99:  # 5-day MA < 20-day MA by 1%
            ma_signal = "bearish"
        else:
            ma_signal = "neutral"

        # Combine signals
        signals = [price_signal, ma_signal]
        bullish_votes = sum(1 for s in signals if s == "bullish")
        bearish_votes = sum(1 for s in signals if s == "bearish")

        if bullish_votes >= 2:
            return "bullish"
        elif bearish_votes >= 2:
            return "bearish"
        else:
            return "neutral"

    def classify_iv_level(self, iv_rank):
        """
        Classify IV level based on IV rank.

        Args:
            iv_rank: IV rank (0-100)

        Returns:
            "low", "high", or "extreme"
        """
        if iv_rank < 50:
            return "low"
        elif iv_rank < 75:
            return "high"
        else:
            return "extreme"

    def classify_vol_trend(self, iv_change_5d):
        """
        Classify volatility trend.

        Args:
            iv_change_5d: 5-day IV change (%)

        Returns:
            "rising", "falling", or "stable"
        """
        if iv_change_5d > 5:
            return "rising"
        elif iv_change_5d < -5:
            return "falling"
        else:
            return "stable"

    def select_strategy(
        self,
        symbol,
        outlook,
        iv_level,
        vol_trend,
        iv_rank,
        vix,
        price
    ):
        """
        Select strategy based on market regime.

        Returns:
            (strategy_name, reasoning, urgency)
        """
        strategy_matrix = {
            ("bullish", "low"): ("Bull Put Spread (Credit)",
                                f"Low IV ({iv_rank:.0f}) = cheap options, sell premium on bullish view"),
            ("bullish", "high"): ("Bull Call Spread (Debit)",
                                f"High IV ({iv_rank:.0f}) = expensive calls, spread reduces cost"),
            ("bullish", "extreme"): ("Long Call (Debit)",
                                    f"Extreme IV ({iv_rank:.0f}) = high vol, long calls benefit from vol rise"),

            ("bearish", "low"): ("Bear Call Spread (Credit)",
                                f"Low IV ({iv_rank:.0f}) = cheap options, sell premium on bearish view"),
            ("bearish", "high"): ("Bear Put Spread (Debit)",
                                f"High IV ({iv_rank:.0f}) = expensive puts, spread reduces cost"),
            ("bearish", "extreme"): ("Long Put (Debit)",
                                    f"Extreme IV ({iv_rank:.0f}) = high vol, long puts benefit from vol rise"),

            ("neutral", "low"): ("Iron Condor (Credit)",
                                f"Low IV ({iv_rank:.0f}) = cheap options, iron condor defines range"),
            ("neutral", "high"): ("Short Straddle (Credit)",
                                 f"High IV ({iv_rank:.0f}) = expensive options, sell premium for income"),
            ("neutral", "extreme"): ("Short Strangle (Credit)",
                                    f"Extreme IV ({iv_rank:.0f}) = very expensive, strangle for max premium"),
        }

        # Get base strategy
        key = (outlook, iv_level)
        if key in strategy_matrix:
            strategy, base_reason = strategy_matrix[key]

            # Adjust for vol trend
            if vol_trend == "rising" and outlook in ["bullish", "bearish"]:
                # Rising vol favors debit strategies
                if iv_level == "high":
                    strategy = strategy.replace("Spread", "Backspread (2:1)")
                    base_reason += f", rising vol amplifies potential"

            elif vol_trend == "falling" and outlook == "neutral":
                # Falling vol favors credit strategies
                base_reason += f", falling vol (IV crush) benefits credit position"

            # Determine urgency
            urgency = "normal"
            if iv_level == "extreme":
                urgency = "high"  # Extreme IV requires immediate action
            elif vol_trend == "rising" and iv_level == "high":
                urgency = "high"  # Rising vol in high IV = urgency

            return strategy, base_reason, urgency

        else:
            return "NO STRATEGY", "Market conditions don't match entry criteria", "none"


def analyze_scenario(
    selector,
    scenario_name,
    symbol,
    price,
    price_change_1d,
    ma5,
    ma20,
    iv_rank,
    vix,
    iv_change_5d
):
    """Analyze a market scenario and select strategy."""
    print(f"\n{'=' * 80}")
    print(f"📊 SCENARIO: {scenario_name}")
    print(f"{'=' * 80}")

    # Classify market regime
    outlook = selector.classify_market_outlook(price_change_1d, ma5, ma20)
    iv_level = selector.classify_iv_level(iv_rank)
    vol_trend = selector.classify_vol_trend(iv_change_5d)

    # Display market data
    print(f"\n📈 MARKET DATA for {symbol}:")
    print(f"  Price: ${price:.2f} ({price_change_1d:+.2f}%)")
    print(f"  Moving Averages: 5-day = ${ma5:.2f}, 20-day = ${ma20:.2f}")
    print(f"  IV Rank: {iv_rank:.1f} ({iv_level.upper()})")
    print(f"  VIX: {vix:.2f}")
    print(f"  IV Change (5d): {iv_change_5d:+.1f}% ({vol_trend.upper()})")

    # Display regime classification
    print(f"\n🎯 MARKET REGIME:")
    print(f"  Outlook: {outlook.upper()}")
    print(f"  IV Level: {iv_level.upper()}")
    print(f"  Volatility Trend: {vol_trend.upper()}")

    # Select strategy
    strategy, reasoning, urgency = selector.select_strategy(
        symbol, outlook, iv_level, vol_trend, iv_rank, vix, price
    )

    # Display result
    print(f"\n✅ SELECTED STRATEGY: {strategy}")
    print(f"   Urgency: {urgency.upper()}")
    print(f"\n💡 WHY?")
    print(f"   {reasoning}")

    # Show what would NOT be selected
    print(f"\n❌ WHY NOT OTHERS?")
    if outlook == "bullish":
        print(f"   - Not bearish strategies: Market is trending up ({price_change_1d:+.2f}%)")
    elif outlook == "bearish":
        print(f"   - Not bullish strategies: Market is trending down ({price_change_1d:+.2f}%)")
    else:  # neutral
        print(f"   - Not directional strategies: Market is range-bound")

    if iv_level == "low":
        print(f"   - Not debit spreads (long calls/puts): IV is low ({iv_rank:.0f}), options are cheap")
    elif iv_level == "high":
        print(f"   - Not naked long options: IV is high ({iv_rank:.0f}), too expensive")

    if vol_trend == "falling" and iv_level == "high":
        print(f"   - Caution on debit strategies: IV falling = IV crush risk")

    return strategy, reasoning


async def main():
    """Run strategy selection simulation for today's market."""

    selector = StrategySelector()

    print("\n📅 CURRENT MARKET CONDITIONS (Simulated)")
    print("Testing various realistic scenarios that could occur today")

    # Scenario 1: Bullish market with low IV (common in stable uptrend)
    analyze_scenario(
        selector,
        "Bullish Uptrend with Low Volatility",
        symbol="SPY",
        price=580.50,
        price_change_1d=1.2,
        ma5=578.00,
        ma20=570.00,
        iv_rank=35.0,
        vix=14.5,
        iv_change_5d=-2.0
    )

    # Scenario 2: Neutral market with high IV (common before earnings/Fed)
    analyze_scenario(
        selector,
        "Sideways with Elevated Volatility",
        symbol="SPY",
        price=580.00,
        price_change_1d=0.1,
        ma5=579.50,
        ma20=581.00,
        iv_rank=62.0,
        vix=22.0,
        iv_change_5d=8.0
    )

    # Scenario 3: Bearish with low IV (market dip, still cheap options)
    analyze_scenario(
        selector,
        "Market Pullback with Low IV",
        symbol="QQQ",
        price=510.00,
        price_change_1d=-1.5,
        ma5=515.00,
        ma20=520.00,
        iv_rank=42.0,
        vix=16.0,
        iv_change_5d=-1.0
    )

    # Scenario 4: Extreme volatility (crash or surge scenario)
    analyze_scenario(
        selector,
        "Extreme Volatility Event",
        symbol="IWM",
        price=220.00,
        price_change_1d=-3.0,
        ma5=225.00,
        ma20=230.00,
        iv_rank=85.0,
        vix=35.0,
        iv_change_5d=25.0
    )

    print("\n" + "=" * 80)
    print("SIMULATION COMPLETE")
    print("=" * 80)
    print("\n📝 KEY TAKEAWAYS:")
    print("1. Strategy selection depends on 3 factors: Outlook, IV Level, Vol Trend")
    print("2. Low IV (<50): Sell premium (credit spreads, iron condors)")
    print("3. High IV (>50): Buy premium with protection (debit spreads)")
    print("4. Extreme IV (>75): Use long options or backspreads")
    print("5. Falling vol: Favor credit strategies (benefit from IV crush)")
    print("6. Rising vol: Favor debit strategies (benefit from vol expansion)")
    print("\n")


if __name__ == "__main__":
    asyncio.run(main())
