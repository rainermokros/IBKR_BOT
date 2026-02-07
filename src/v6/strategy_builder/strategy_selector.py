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
- IV skew (put/call ratio)
"""

from dataclasses import dataclass
from datetime import datetime, date, timedelta
from typing import List, Dict, Optional
from loguru import logger

from v6.strategy_builder.builders import IronCondorBuilder, VerticalSpreadBuilder
from v6.strategy_builder.models import Strategy
from v6.data.underlying_price import UnderlyingPriceService
from v6.data.option_snapshots import OptionSnapshotsTable


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

    def __init__(self, price_service: Optional[UnderlyingPriceService] = None):
        """
        Initialize strategy builders.

        Args:
            price_service: Optional UnderlyingPriceService for consistent pricing
        """
        self.ic_builder = IronCondorBuilder()
        self.vsb_builder = VerticalSpreadBuilder()
        self.price_service = price_service

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
        """Build Iron Condor with skew-aware strike selection."""
        # Get underlying price from centralized service or fallback to Delta Lake
        if self.price_service:
            try:
                underlying_price = await self.price_service.get_price(symbol)
            except Exception as e:
                logger.warning(f"Price service failed for {symbol}: {e}, using Delta Lake fallback")
                underlying_price = await self._get_underlying_from_deltalake(symbol)
        else:
            underlying_price = await self._get_underlying_from_deltalake(symbol)

        # Calculate skew ratio
        skew_ratio = await self._calculate_skew_ratio(symbol, underlying_price, target_dte)

        # Build iron condor with skew-aware params
        params = {
            'dte': target_dte,
            'put_width': 10,
            'call_width': 10,
            'quantity': quantity,
            'skew_ratio': skew_ratio,
        }

        strategy = await self.ic_builder.build(symbol, underlying_price, params)

        # Add skew metrics to metadata
        strategy.metadata['skew_ratio'] = skew_ratio
        strategy.metadata['skew_interpretation'] = self._interpret_skew(skew_ratio)

        return strategy

    async def _build_bull_put_spread(
        self,
        symbol: str,
        quantity: int,
        target_dte: int,
        use_smart_lookup: bool
    ) -> Strategy:
        """Build Bull Put Spread with skew-aware strike selection."""
        # Get underlying price from centralized service or fallback to Delta Lake
        if self.price_service:
            try:
                underlying_price = await self.price_service.get_price(symbol)
            except Exception as e:
                logger.warning(f"Price service failed for {symbol}: {e}, using Delta Lake fallback")
                underlying_price = await self._get_underlying_from_deltalake(symbol)
        else:
            underlying_price = await self._get_underlying_from_deltalake(symbol)

        # Calculate skew ratio
        skew_ratio = await self._calculate_skew_ratio(symbol, underlying_price, target_dte)

        # Build bull put spread with skew-aware params
        params = {
            'direction': 'BEAR',
            'width': 10,
            'dte': target_dte,
            'quantity': quantity,
            'skew_ratio': skew_ratio,
        }

        strategy = self.vsb_builder.build(symbol, underlying_price, params)

        # Add skew metrics to metadata
        strategy.metadata['skew_ratio'] = skew_ratio
        strategy.metadata['skew_interpretation'] = self._interpret_skew(skew_ratio)

        return strategy

    async def _get_underlying_from_deltalake(self, symbol: str) -> float:
        """Fallback: estimate underlying price from Delta Lake option snapshots."""
        import polars as pl
        from deltalake import DeltaTable
        from pathlib import Path

        # Use string manipulation to handle the double v6 in the path
        # __file__ is /home/bigballs/project/bot/v6/src/v6/strategy_builder/strategy_selector.py
        # Split on '/src/v6/' to get the v6 project root: /home/bigballs/project/bot/v6
        this_file = Path(__file__)
        project_root = Path(str(this_file).split('/src/v6/')[0])
        table_path = project_root / 'data' / 'lake' / 'option_snapshots'

        dt = DeltaTable(str(table_path))
        df = pl.from_pandas(dt.to_pandas())
        symbol_df = df.filter(pl.col('symbol') == symbol)
        strikes = symbol_df.select('strike').unique().sort('strike').get_column('strike').to_list()
        underlying_price = (min(strikes) + max(strikes)) / 2
        logger.debug(f"Estimated {symbol} price from Delta Lake: ${underlying_price:.2f}")
        return underlying_price

    async def _build_bear_call_spread(
        self,
        symbol: str,
        quantity: int,
        target_dte: int,
        use_smart_lookup: bool
    ) -> Strategy:
        """Build Bear Call Spread with skew-aware strike selection."""
        from v6.strategy_builder.models import LegSpec, OptionRight, LegAction, Strategy, StrategyType

        # Get underlying price from centralized service or fallback to Delta Lake
        if self.price_service:
            try:
                underlying_price = await self.price_service.get_price(symbol)
            except Exception as e:
                logger.warning(f"Price service failed for {symbol}: {e}, using Delta Lake fallback")
                underlying_price = await self._get_underlying_from_deltalake(symbol)
        else:
            underlying_price = await self._get_underlying_from_deltalake(symbol)

        # Calculate skew ratio
        skew_ratio = await self._calculate_skew_ratio(symbol, underlying_price, target_dte)

        # Bear call spread: Sell OTM call, buy higher strike call (credit spread)
        width = 10
        expiration = date.today() + timedelta(days=target_dte)

        # Short strike at or slightly above current price (OTM for bearish view)
        short_strike = round((underlying_price * 1.02) / 5) * 5
        long_strike = short_strike + width

        legs = [
            # Short Call (OTM, receives premium)
            LegSpec(
                right=OptionRight.CALL,
                strike=short_strike,
                quantity=quantity,
                action=LegAction.SELL,
                expiration=expiration
            ),
            # Long Call (higher strike, protection)
            LegSpec(
                right=OptionRight.CALL,
                strike=long_strike,
                quantity=quantity,
                action=LegAction.BUY,
                expiration=expiration
            ),
        ]

        strategy = Strategy(
            strategy_id=f"BCS_{symbol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            symbol=symbol,
            strategy_type=StrategyType.VERTICAL_SPREAD,
            legs=legs,
            entry_time=datetime.now(),
            status="OPEN",
            metadata={
                'strategy_name': 'Bear Call Spread',
                'direction': 'BEAR_CALL_CREDIT',
                'width': width,
                'dte': target_dte,
                'quantity': quantity,
                'underlying_price': underlying_price,
                'short_strike': short_strike,
                'long_strike': long_strike,
                'skew_ratio': skew_ratio,
                'skew_interpretation': self._interpret_skew(skew_ratio),
            }
        )

        logger.info(f"Built Bear Call Spread for {symbol}: short ${short_strike} call, long ${long_strike} call")
        return strategy

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

    async def _calculate_skew_ratio(
        self,
        symbol: str,
        underlying_price: float,
        target_dte: int
    ) -> float:
        """
        Calculate IV skew ratio (put IV / call IV) for the symbol.

        Args:
            symbol: Underlying symbol
            underlying_price: Current underlying price
            target_dte: Target days to expiration

        Returns:
            Skew ratio (>1.0 = put skew elevated, <1.0 = call skew elevated)
        """
        from v6.strategy_builder.smart_strike_selector import SmartStrikeSelector

        # Initialize option snapshots table
        snapshots = OptionSnapshotsTable()
        expiry = date.today() + timedelta(days=target_dte)

        # Create IV lookup function
        def get_iv_for_skew(strike: float, right: str) -> float:
            iv = snapshots.get_iv_for_strike(symbol, strike, right, expiry)
            return iv if iv is not None else 0.20  # Default to 20% if not found

        # Calculate skew using SmartStrikeSelector
        selector = SmartStrikeSelector(days_to_expiration=target_dte)
        skew_ratio = selector.calculate_skew_ratio(
            symbol=symbol,
            underlying_price=underlying_price,
            target_dte=target_dte,
            get_iv_func=get_iv_for_skew,
        )

        return skew_ratio

    def _interpret_skew(self, skew_ratio: float) -> str:
        """
        Interpret skew ratio into human-readable form.

        Args:
            skew_ratio: IV put/call ratio

        Returns:
            String interpretation
        """
        if skew_ratio > 1.2:
            return 'high_put_skew'
        elif skew_ratio < 0.8:
            return 'high_call_skew'
        else:
            return 'neutral'
