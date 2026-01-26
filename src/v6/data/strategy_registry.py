"""
Strategy Registry for tracking active option contracts.

This registry tracks which contracts are in active strategies (Iron Condors,
vertical spreads, etc.) to determine which contracts should be streamed
(real-time) vs queued (batch processing).

Active contracts consume streaming slots but get immediate updates.
Non-active contracts are queued and processed periodically (0 slots).
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from loguru import logger
import polars as pl


@dataclass(slots=True)
class ActiveContract:
    """An active option contract in a strategy."""
    conid: int
    symbol: str
    right: str  # CALL or PUT
    strike: float
    expiry: str
    strategy_id: int
    added_at: datetime = field(default_factory=datetime.now)


class StrategyRegistry:
    """
    Registry of active option contracts.

    Tracks which contracts are in active strategies to determine
    streaming vs queueing decision.

    **Two-Tier Storage:**
    1. In-memory: Fast lookup (self._active_contracts)
    2. Delta Lake: Persistent storage (active_strategies table)

    **Thread-Safe:**
    Uses asyncio.Lock for concurrent access protection.
    """

    def __init__(self, delta_lake_path: str = "data/lake/active_strategies"):
        """
        Initialize registry.

        Args:
            delta_lake_path: Path to Delta Lake table for persistence
        """
        self.delta_lake_path = Path(delta_lake_path)
        self._active_contracts: dict[int, ActiveContract] = {}
        self._lock = asyncio.Lock()
        self._initialized = False

    async def initialize(self) -> None:
        """
        Load active contracts from Delta Lake on startup.

        Called once at system startup to rebuild in-memory cache
        from persistent storage.
        """
        if self._initialized:
            return

        async with self._lock:
            # Check if table exists
            if not self.delta_lake_path.exists():
                logger.info("No active strategies table found (empty registry)")
                self._initialized = True
                return

            # Load from Delta Lake
            try:
                import deltalake as dl

                dt = dl.DeltaTable(str(self.delta_lake_path))
                df_pl = pl.from_pandas(dt.to_pandas())

                # Build in-memory cache
                for row in df_pl.to_dicts():
                    # Only load active contracts (not removed)
                    if row.get('removed_at') is None:
                        self._active_contracts[row['conid']] = ActiveContract(
                            conid=row['conid'],
                            symbol=row['symbol'],
                            right=row['right'],
                            strike=row['strike'],
                            expiry=row['expiry'],
                            strategy_id=row['strategy_id'],
                            added_at=datetime.fromisoformat(row['added_at'])
                        )

                logger.info(f"✓ Loaded {len(self._active_contracts)} active contracts from registry")
                self._initialized = True

            except Exception as e:
                logger.error(f"Failed to load active strategies: {e}")
                self._initialized = True

    def is_active(self, conid: int) -> bool:
        """
        Check if contract is in active strategy.

        Args:
            conid: IB contract ID

        Returns:
            True if contract should be streamed (active strategy)
            False if contract should be queued (non-essential)
        """
        return conid in self._active_contracts

    async def add_active(
        self,
        conid: int,
        symbol: str,
        right: str,
        strike: float,
        expiry: str,
        strategy_id: int
    ) -> None:
        """
        Add contract to active registry.

        Called when strategy enters a position.

        Args:
            conid: IB contract ID
            symbol: Underlying symbol
            right: CALL or PUT
            strike: Strike price
            expiry: Expiration date (IB format)
            strategy_id: Strategy ID this contract belongs to
        """
        async with self._lock:
            # Create active contract record
            contract = ActiveContract(
                conid=conid,
                symbol=symbol,
                right=right,
                strike=strike,
                expiry=expiry,
                strategy_id=strategy_id
            )

            # Add to in-memory cache
            self._active_contracts[conid] = contract

            # Persist to Delta Lake
            await self._persist_contract(contract)

            logger.info(f"✓ Added active contract: {symbol} {right} {strike} (conid: {conid})")

    async def remove_active(self, conid: int) -> None:
        """
        Remove contract from active registry.

        Called when strategy exits a position.

        Args:
            conid: IB contract ID to remove
        """
        async with self._lock:
            if conid not in self._active_contracts:
                logger.warning(f"Contract {conid} not in active registry")
                return

            # Remove from in-memory cache
            del self._active_contracts[conid]

            # Update Delta Lake (soft delete: set removed_at timestamp)
            await self._mark_removed(conid)

            logger.info(f"✓ Removed active contract: {conid}")

    async def get_all_active(self) -> list[ActiveContract]:
        """
        Get all active contracts.

        Returns:
            List of all active contracts
        """
        async with self._lock:
            return list(self._active_contracts.values())

    async def _persist_contract(self, contract: ActiveContract) -> None:
        """
        Persist contract to Delta Lake.

        Args:
            contract: ActiveContract to persist
        """
        try:
            import deltalake as dl

            # Create table if not exists
            if not self.delta_lake_path.exists():
                self._create_table()

            # Insert record (without removed_at field for active contracts)
            df = pl.DataFrame({
                'conid': [contract.conid],
                'symbol': [contract.symbol],
                'right': [contract.right],
                'strike': [contract.strike],
                'expiry': [contract.expiry],
                'strategy_id': [contract.strategy_id],
                'added_at': [contract.added_at.isoformat()],
                'removed_at': [None]
            }, schema={
                'conid': pl.Int64,
                'symbol': pl.String,
                'right': pl.String,
                'strike': pl.Float64,
                'expiry': pl.String,
                'strategy_id': pl.Int64,
                'added_at': pl.String,
                'removed_at': pl.String
            })

            dl.write_deltalake(
                str(self.delta_lake_path),
                df,
                mode='append'
            )

        except Exception as e:
            logger.error(f"Failed to persist active contract: {e}")

    async def _mark_removed(self, conid: int) -> None:
        """
        Mark contract as removed in Delta Lake.

        Args:
            conid: Contract ID to mark removed
        """
        try:
            import deltalake as dl

            dt = dl.DeltaTable(str(self.delta_lake_path))

            # Update removed_at timestamp (only for active records)
            dt.update(
                predicate=f"conid = {conid} AND removed_at IS NULL",
                updates={"removed_at": datetime.now().isoformat()}
            )

        except Exception as e:
            logger.error(f"Failed to mark contract removed: {e}")

    def _create_table(self) -> None:
        """Create active_strategies Delta Lake table."""
        import deltalake as dl

        # Create empty table with proper schema
        df = pl.DataFrame({
            'conid': pl.Series([], dtype=pl.Int64),
            'symbol': pl.Series([], dtype=pl.String),
            'right': pl.Series([], dtype=pl.String),
            'strike': pl.Series([], dtype=pl.Float64),
            'expiry': pl.Series([], dtype=pl.String),
            'strategy_id': pl.Series([], dtype=pl.Int64),
            'added_at': pl.Series([], dtype=pl.String),
            'removed_at': pl.Series([], dtype=pl.String)
        })

        dl.write_deltalake(
            str(self.delta_lake_path),
            df,
            mode='overwrite'
        )

        logger.info(f"✓ Created active_strategies table: {self.delta_lake_path}")
