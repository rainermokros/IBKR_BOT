"""
Strategy Selector - Build and Rank All Strategies

Analyzes all available strategies for a symbol and selects the best
risk/reward opportunity.

Strategies evaluated:
1. Iron Condor (neutral)
2. Bull Put Spread (bullish)
3. Bear Call Spread (bearish)

Metrics:
- Credit received
- Max risk (spread width)
- Risk/reward ratio
- Probability of success (from delta)
- Expected return
- IV rank context
"""

from dataclasses import dataclass
from datetime import datetime
from typing import List, Dict, Optional
from loguru import logger

from v6.strategy_builder.builders import IronCondorBuilder, VerticalSpreadBuilder
from v6.strategy_builder.models import Strategy


@dataclass(slots=True)
class StrategyAnalysis:
    """Analysis results for a strategy."""
    strategy: Strategy
    strategy_name: str
    credit: float  # Premium collected
    max_risk: float  # Maximum loss
    risk_reward_ratio: float  # Max risk / Credit
    probability_of_success: float  # From delta (0-100%)
    expected_return: float  # Credit × POS - (Max Risk × (1-POS))
    expected_return_pct: float  # Expected return / Max risk
    iv_rank: float
    delta_target: float
    score: float  # Composite score


class StrategySelector:
    """
    Build and rank all strategies to find best risk/reward.

    Process:
    1. Build all available strategies
    2. Calculate risk/reward metrics
    3. Score each strategy
    4. Rank and recommend best
    """

    def __init__(self):
        """Initialize strategy builders."""
        self.ic_builder = IronCondorBuilder()
        self.vsb_builder = VerticalSpreadBuilder()

    async def analyze_all_strategies(
        self,
        symbol: str,
        quantity: int = 1,
        target_dte: int = 45,
        use_smart_lookup: bool = True
    ) -> List[StrategyAnalysis]:
        """
        Build and analyze all strategies for symbol.

        Args:
            symbol: Underlying symbol (SPY, QQQ, IWM)
            quantity: Number of contracts
            target_dte: Target days to expiration
            use_smart_lookup: Use smart strike lookup (vs brute force)

        Returns:
            List of strategy analyses, ranked by score
        """
        logger.info("=" * 80)
        logger.info(f"STRATEGY SELECTOR: Analyzing all strategies for {symbol}")
        logger.info("=" * 80)

        analyses = []

        # Try to build each strategy
        strategies_to_build = [
            ("Iron Condor", self._build_iron_condor),
            ("Bull Put Spread", self._build_bull_put_spread),
            ("Bear Call Spread", self._build_bear_call_spread),
        ]

        for strategy_name, builder_func in strategies_to_build:
            try:
                logger.info(f"\n{'='*80}")
                logger.info(f"Building {strategy_name}...")
                logger.info(f"{'='*80}")

                strategy = await builder_func(
                    symbol=symbol,
                    quantity=quantity,
                    target_dte=target_dte,
                    use_smart_lookup=use_smart_lookup
                )

                analysis = self._analyze_strategy(strategy, strategy_name)
                analyses.append(analysis)

                self._print_analysis(analysis)

            except Exception as e:
                logger.warning(f"❌ {strategy_name} failed: {e}")
                continue

        # Score and rank
        logger.info(f"\n{'='*80}")
        logger.info("RANKING STRATEGIES")
        logger.info(f"{'='*80}")

        ranked = self._score_and_rank(analyses)

        self._print_ranking(ranked)

        return ranked

    async def _build_iron_condor(
        self,
        symbol: str,
        quantity: int,
        target_dte: int,
        use_smart_lookup: bool
    ) -> Strategy:
        """Build Iron Condor."""
        # Estimate underlying price from option data
        import polars as pl
        from deltalake import DeltaTable

        dt = DeltaTable('data/lake/option_snapshots')
        df = pl.from_pandas(dt.to_pandas())
        symbol_df = df.filter(pl.col('symbol') == symbol)
        strikes = symbol_df.select('strike').unique().sort('strike').get_column('strike').to_list()
        underlying_price = (min(strikes) + max(strikes)) / 2

        # Build iron condor
        params = {
            'dte': target_dte,
            'put_width': 10,
            'call_width': 10,
            'quantity': quantity,
        }

        return await self.ic_builder.build(symbol, underlying_price, params)

    async def _build_bull_put_spread(
        self,
        symbol: str,
        quantity: int,
        target_dte: int,
        use_smart_lookup: bool
    ) -> Strategy:
        """Build Bull Put Spread (vertical spread with BEAR direction = credit put spread)."""
        import polars as pl
        from deltalake import DeltaTable

        dt = DeltaTable('data/lake/option_snapshots')
        df = pl.from_pandas(dt.to_pandas())
        symbol_df = df.filter(pl.col('symbol') == symbol)
        strikes = symbol_df.select('strike').unique().sort('strike').get_column('strike').to_list()
        underlying_price = (min(strikes) + max(strikes)) / 2

        # Build bull put spread (vertical spread, BEAR direction = put spread)
        params = {
            'direction': 'BEAR',
            'width': 10,
            'dte': target_dte,
            'quantity': quantity,
        }

        return self.vsb_builder.build(symbol, underlying_price, params)

    async def _build_bear_call_spread(
        self,
        symbol: str,
        quantity: int,
        target_dte: int,
        use_smart_lookup: bool
    ) -> Strategy:
        """Build Bear Call Spread (not yet implemented)."""
        raise NotImplementedError("Bear call spread not yet implemented with current builders")

    def _analyze_strategy(
        self,
        strategy: Strategy,
        strategy_name: str
    ) -> StrategyAnalysis:
        """
        Analyze strategy risk/reward metrics.

        For credit strategies:
        - Credit = Premium collected (positive cash flow)
        - Max Risk = Spread width - Credit
        - R/R Ratio = Max Risk / Credit
        - POS (Probability of Success) = 100 - (|short_delta| × 100)
        - Expected Return = Credit × POS% - Risk × (1-POS)%
        """
        metadata = strategy.metadata
        iv_rank = metadata.get('iv_rank', 50.0)
        delta_target = metadata.get('delta_target', 0.20)

        # Get quantity from strategy legs or metadata
        quantity = metadata.get('quantity', 1)
        if strategy.legs:
            quantity = strategy.legs[0].quantity

        # Calculate metrics based on strategy type
        if strategy.strategy_type == "iron_condor":
            # Iron Condor: 2 wings
            put_wing = metadata.get('put_width', 0)
            call_wing = metadata.get('call_width', 0)

            # Estimate credit (would need mid prices in production)
            # For now, estimate as 50% of wing width
            put_credit = put_wing * 0.5
            call_credit = call_wing * 0.5
            credit = (put_credit + call_credit) * 100 * quantity

            # Max risk = Wing width - Credit (for each wing)
            put_risk = (put_wing - put_credit) * 100 * quantity
            call_risk = (call_wing - call_credit) * 100 * quantity
            max_risk = max(put_risk, call_risk)

        elif strategy.strategy_type == "vertical_spread":
            # Credit Spread: 1 wing
            spread_width = metadata.get('width', 10)

            # Estimate credit (50% of spread width)
            credit = spread_width * 0.5 * 100 * quantity

            # Max risk = Spread width - Credit
            max_risk = (spread_width - (spread_width * 0.5)) * 100 * quantity

        else:
            # Default/unknown
            credit = 100.0
            max_risk = 1000.0

        # Avoid division by zero
        if credit <= 0:
            credit = 100.0
        if max_risk <= 0:
            max_risk = 1000.0

        # Risk/reward ratio
        risk_reward_ratio = max_risk / credit

        # Probability of success from delta
        # For short options: POS ≈ 100 - (|delta| × 100)
        if 'short_put_delta' in metadata:
            short_delta = abs(metadata['short_put_delta'])
        elif 'short_call_delta' in metadata:
            short_delta = abs(metadata['short_call_delta'])
        else:
            short_delta = delta_target

        probability_of_success = 100 - (short_delta * 100)

        # Expected return
        expected_return = (credit * probability_of_success / 100) - \
                         (max_risk * (1 - probability_of_success / 100))

        expected_return_pct = (expected_return / max_risk * 100)

        # Composite score (0-100)
        # Higher is better
        score = self._calculate_score(
            credit=credit,
            max_risk=max_risk,
            probability_of_success=probability_of_success,
            expected_return_pct=expected_return_pct,
            iv_rank=iv_rank
        )

        return StrategyAnalysis(
            strategy=strategy,
            strategy_name=strategy_name,
            credit=credit,
            max_risk=max_risk,
            risk_reward_ratio=risk_reward_ratio,
            probability_of_success=probability_of_success,
            expected_return=expected_return,
            expected_return_pct=expected_return_pct,
            iv_rank=iv_rank,
            delta_target=delta_target,
            score=score
        )

    def _calculate_score(
        self,
        credit: float,
        max_risk: float,
        probability_of_success: float,
        expected_return_pct: float,
        iv_rank: float
    ) -> float:
        """
        Calculate composite strategy score (0-100).

        Scoring factors:
        1. Risk/Reward Ratio (30%): Lower is better (prefer less risk per dollar)
        2. Probability of Success (30%): Higher is better
        3. Expected Return % (25%): Higher is better
        4. IV Rank Context (15%): Adjust for volatility environment

        Returns:
            Score from 0-100
        """
        # Risk/Reward score (0-100)
        # Ideal R/R < 3: 100 points
        # R/R = 5: 50 points
        # R/R >= 10: 0 points
        rr_score = max(0, 100 - (max_risk / credit - 3) * 20)
        rr_score = min(100, rr_score)

        # Probability of Success score (0-100)
        # POS >= 80%: 100 points
        # POS = 70%: 50 points
        # POS < 50%: 0 points
        pos_score = max(0, (probability_of_success - 50) * 5)
        pos_score = min(100, pos_score)

        # Expected Return % score (0-100)
        # ER >= 20%: 100 points
        # ER = 10%: 50 points
        # ER <= 0%: 0 points
        er_score = max(0, expected_return_pct * 5)
        er_score = min(100, er_score)

        # IV Rank adjustment (0-100)
        # Moderate IV (25-75): Best for sellers (100 points)
        # Very high IV (75-100): Good but expensive (75 points)
        # Low IV (0-25): Bad for credit strategies (25 points)
        if 25 <= iv_rank <= 75:
            iv_score = 100
        elif iv_rank > 75:
            iv_score = 75
        else:
            iv_score = 25

        # Weighted composite score
        score = (
            rr_score * 0.30 +
            pos_score * 0.30 +
            er_score * 0.25 +
            iv_score * 0.15
        )

        return round(score, 1)

    def _score_and_rank(
        self,
        analyses: List[StrategyAnalysis]
    ) -> List[StrategyAnalysis]:
        """Sort analyses by score (descending)."""
        return sorted(analyses, key=lambda x: x.score, reverse=True)

    def _print_analysis(self, analysis: StrategyAnalysis):
        """Print detailed analysis for a strategy."""
        logger.info(f"\n📊 {analysis.strategy_name} Analysis:")
        logger.info(f"   Credit: ${analysis.credit:.2f}")
        logger.info(f"   Max Risk: ${analysis.max_risk:.2f}")
        logger.info(f"   R/R Ratio: {analysis.risk_reward_ratio:.2f}:1")
        logger.info(f"   Probability of Success: {analysis.probability_of_success:.1f}%")
        logger.info(f"   Expected Return: ${analysis.expected_return:.2f} ({analysis.expected_return_pct:.1f}%)")
        logger.info(f"   IV Rank: {analysis.iv_rank:.0f}%")
        logger.info(f"   Delta Target: {analysis.delta_target:.2f}")
        logger.info(f"   Score: {analysis.score:.1f}/100")

    def _print_ranking(self, ranked: List[StrategyAnalysis]):
        """Print ranked strategies."""
        logger.info(f"\n🏆 FINAL RANKING:")

        for i, analysis in enumerate(ranked, 1):
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "  "
            logger.info(f"\n{medal} #{i} - {analysis.strategy_name}")
            logger.info(f"   Score: {analysis.score:.1f}/100")
            logger.info(f"   R/R: {analysis.risk_reward_ratio:.2f}:1 | POS: {analysis.probability_of_success:.1f}%")
            logger.info(f"   Exp Return: ${analysis.expected_return:.2f} ({analysis.expected_return_pct:.1f}%)")

        if ranked:
            best = ranked[0]
            logger.info(f"\n{'='*80}")
            logger.info(f"✅ RECOMMENDED: {best.strategy_name}")
            logger.info(f"   Score: {best.score:.1f}/100")
            logger.info(f"   Risk/Reward: ${best.max_risk:.2f} risk for ${best.credit:.2f} credit")
            logger.info(f"   Probability of Success: {best.probability_of_success:.1f}%")
            logger.info(f"   Expected Return: ${best.expected_return:.2f} ({best.expected_return_pct:.1f}%)")
            logger.info(f"{'='*80}")

    async def get_best_strategy(
        self,
        symbol: str,
        quantity: int = 1,
        target_dte: int = 45
    ) -> Optional[StrategyAnalysis]:
        """
        Get the best strategy for a symbol.

        Args:
            symbol: Underlying symbol
            quantity: Number of contracts
            target_dte: Target days to expiration

        Returns:
            Best strategy analysis, or None if no strategies built
        """
        ranked = await self.analyze_all_strategies(
            symbol=symbol,
            quantity=quantity,
            target_dte=target_dte,
            use_smart_lookup=True
        )

        return ranked[0] if ranked else None
