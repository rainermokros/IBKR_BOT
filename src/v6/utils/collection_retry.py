"""
Retry utilities for option snapshot collection.

Provides exponential backoff retry logic with automatic error classification
and queue management for backfill.
"""

import asyncio
import random
from datetime import datetime
from typing import Callable, TypeVar, Optional
from loguru import logger

from v6.data.collection_queue import CollectionQueue


T = TypeVar('T')


class CollectionError(Exception):
    """Base exception for collection errors."""
    def __init__(self, message: str, error_type: str, should_retry: bool = True):
        self.message = message
        self.error_type = error_type
        self.should_retry = should_retry
        super().__init__(message)


def classify_error(error: Exception) -> CollectionError:
    """
    Classify an exception to determine retry strategy.

    Args:
        error: The exception to classify

    Returns:
        CollectionError with appropriate error type and retry flag
    """
    error_str = str(error).lower()

    # Network/connection errors - always retry
    if any(term in error_str for term in [
        'timeout', 'connection', 'network', 'socket',
        'not connected', 'disconnected', 'connection lost'
    ]):
        return CollectionError(
            str(error),
            error_type='connection',
            should_retry=True
        )

    # IB Gateway errors
    if 'error 200' in error_str:
        # Contract doesn't exist - expected, don't retry
        return CollectionError(
            str(error),
            error_type='contract_not_found',
            should_retry=False
        )

    if 'error 502' in error_str:
        # Connection lost - retry
        return CollectionError(
            str(error),
            error_type='connection',
            should_retry=True
        )

    # No data available - might be temporary, retry
    if any(term in error_str for term in [
        'no data', 'no chains', 'no security definition'
    ]):
        return CollectionError(
            str(error),
            error_type='no_data',
            should_retry=True
        )

    # Authentication errors - don't retry (need fix)
    if any(term in error_str for term in [
        'auth', 'unauthorized', 'not authorized'
    ]):
        return CollectionError(
            str(error),
            error_type='auth',
            should_retry=False
        )

    # Rate limiting - retry with backoff
    if any(term in error_str for term in [
        'rate limit', 'too many requests', 'pacing'
    ]):
        return CollectionError(
            str(error),
            error_type='rate_limit',
            should_retry=True
        )

    # Unknown errors - retry with caution
    return CollectionError(
        str(error),
        error_type='unknown',
        should_retry=True
    )


async def retry_with_backoff(
    func: Callable[..., T],
    symbol: str,
    queue: CollectionQueue,
    target_time: datetime,
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0
) -> Optional[T]:
    """
    Execute function with exponential backoff retry.

    Args:
        func: Async function to execute
        symbol: ETF symbol (for queue logging)
        queue: CollectionQueue for failures
        target_time: Scheduled time for this collection
        max_retries: Maximum retry attempts
        base_delay: Initial delay in seconds
        max_delay: Maximum delay between retries

    Returns:
        Function result if successful, None if all retries exhausted
    """
    last_error = None

    for attempt in range(max_retries):
        try:
            if attempt > 0:
                delay = min(base_delay * (2 ** attempt) + random.uniform(0, 1), max_delay)
                logger.info(f"Retry {attempt + 1}/{max_retries} for {symbol} after {delay:.1f}s delay...")
                await asyncio.sleep(delay)

            result = await func()
            return result

        except Exception as e:
            classified = classify_error(e)
            last_error = classified

            logger.warning(f"Attempt {attempt + 1}/{max_retries} failed: {classified.error_type}")

            # Don't retry if error is not retryable (e.g., Error 200)
            if not classified.should_retry:
                logger.debug(f"Non-retryable error: {classified.error_type}")
                raise classified

            # Continue to next retry

    # All retries exhausted - add to backfill queue
    if last_error and last_error.should_retry:
        queue.add_failure(
            symbol=symbol,
            target_time=target_time,
            error_type=last_error.error_type,
            error_message=last_error.message,
            max_retries=5
        )

    logger.error(f"All {max_retries} retries exhausted for {symbol}")
    return None


async def retry_symbol_collection(
    collection_func: Callable,
    symbol: str,
    queue: CollectionQueue,
    target_time: datetime,
    max_retries: int = 3
) -> bool:
    """
    Retry collection for a single symbol with error handling.

    Args:
        collection_func: Function that performs the collection
        symbol: ETF symbol to collect
        queue: CollectionQueue for failures
        target_time: Scheduled time for this collection
        max_retries: Maximum retry attempts

    Returns:
        True if collection succeeded, False otherwise
    """
    try:
        result = await retry_with_backoff(
            func=collection_func,
            symbol=symbol,
            queue=queue,
            target_time=target_time,
            max_retries=max_retries
        )

        return result is not None

    except CollectionError as e:
        # Non-retryable error (e.g., Error 200)
        if e.error_type != 'contract_not_found':
            logger.warning(f"Non-retryable error for {symbol}: {e.error_type}")
        return False

    except Exception as e:
        logger.error(f"Unexpected error for {symbol}: {e}")
        return False
