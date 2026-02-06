#!/usr/bin/env python3
"""
Run Strategy Analysis - Using v6 StrategySelector Infrastructure

Analyzes all strategies (Iron Condor, Bull Put, Bear Call) for SPY, QQQ, IWM
using the proper v6 StrategySelector infrastructure.

This replaces the obsolete run_strategy_builder.py which used blind percentages.

Proper v6 Infrastructure:
- StrategySelector: Analyzes and scores strategies
- IronCondorBuilder, VerticalSpreadBuilder: Build strategies
- Scoring based on: credit, risk/reward, probability of success, IV rank

Schedule: 9:45 AM (pre-market)
Usage:
    PYTHONPATH=/home/bigballs/project/bot/v6/src python scripts/run_strategy_analysis.py
"""

import asyncio
import sys
from datetime import datetime
from pathlib import Path

from loguru import logger

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from v6.strategy_builder.strategy_selector import StrategySelector


async def analyze_symbol(selector: StrategySelector, symbol: str) -> dict:
    """
    Analyze all strategies for a symbol.

    Returns:
        dict: Analysis results with best strategy
    """
    logger.info(f"\n{'='*80}")
    logger.info(f"ANALYZING {symbol}")
    logger.info(f"{'='*80}")

    try:
        # Analyze all strategies
        analyses = await selector.analyze_all_strategies(
            symbol=symbol,
            quantity=1,
            target_dte=45,
            use_smart_lookup=True
        )

        if not analyses:
            logger.warning(f"No strategies could be built for {symbol}")
            return {
                'symbol': symbol,
                'success': False,
                'reason': 'No strategies built'
            }

        # Show results
        logger.info(f"\nBuilt {len(analyses)} strategies for {symbol}")
        logger.info("-" * 80)

        for analysis in analyses:
            logger.info(f"\n{analysis.strategy_name}:")
            logger.info(f"  Score: {analysis.score:.1f}/100")
            logger.info(f"  Credit: ${analysis.credit:.2f}")
            logger.info(f"  Max Risk: ${analysis.max_risk:.2f}")
            logger.info(f"  R/R Ratio: 1:{analysis.risk_reward_ratio:.2f}")
            logger.info(f"  Prob. Success: {analysis.probability_of_success:.1f}%")
            logger.info(f"  Expected Return: {analysis.expected_return_pct:.1f}%")
            logger.info(f"  IV Rank: {analysis.iv_rank:.1f}")

        # Find best strategy
        best = max(analyses, key=lambda a: a.score)

        logger.info(f"\n{'='*80}")
        logger.success(f"BEST STRATEGY for {symbol}: {best.strategy_name}")
        logger.success(f"Score: {best.score:.1f}/100")
        logger.info(f"{'='*80}")

        return {
            'symbol': symbol,
            'success': True,
            'best_strategy': best.strategy_name,
            'score': best.score,
            'credit': best.credit,
            'max_risk': best.max_risk,
            'strategy': best.strategy,
            'all_analyses': analyses
        }

    except Exception as e:
        logger.error(f"Failed to analyze {symbol}: {e}")
        import traceback
        traceback.print_exc()
        return {
            'symbol': symbol,
            'success': False,
            'reason': str(e)
        }


async def main():
    """Run strategy analysis for all symbols."""

    logger.info("=" * 80)
    logger.info("STRATEGY ANALYSIS - v6 StrategySelector Infrastructure")
    logger.info("=" * 80)
    logger.info(f"Time: {datetime.now()}")
    logger.info("")

    selector = StrategySelector()

    symbols = ["SPY", "QQQ", "IWM"]
    results = []

    for symbol in symbols:
        result = await analyze_symbol(selector, symbol)
        results.append(result)

    # Summary
    logger.info("\n" + "=" * 80)
    logger.info("STRATEGY ANALYSIS SUMMARY")
    logger.info("=" * 80)

    successful = [r for r in results if r['success']]
    failed = [r for r in results if not r['success']]

    logger.info(f"\n✓ Successfully analyzed: {len(successful)}/{len(symbols)}")

    for result in successful:
        logger.info(f"  {result['symbol']}: {result['best_strategy']} (Score: {result['score']:.1f})")

    if failed:
        logger.warning(f"\n✗ Failed: {len(failed)}/{len(symbols)}")
        for result in failed:
            logger.warning(f"  {result['symbol']}: {result['reason']}")

    # Recommendations for execution
    logger.info("\n" + "=" * 80)
    logger.info("EXECUTION RECOMMENDATIONS")
    logger.info("=" * 80)

    executable_strategies = [
        r for r in successful
        if r['score'] >= 70  # Only execute high-quality strategies
    ]

    if executable_strategies:
        logger.info(f"\n✓ {len(executable_strategies)} strategies qualify for execution (score >= 70):")
        for result in executable_strategies:
            logger.info(f"  {result['symbol']}: {result['best_strategy']} (${result['credit']:.2f} credit)")
        logger.info("\nNext step: Run execute_best_strategies.py at 10:00 AM")
    else:
        logger.info("\n✗ No strategies meet execution threshold (score >= 70)")
        logger.info("Recommendation: Do NOT execute strategies today")

    return 0 if len(successful) == len(symbols) else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
