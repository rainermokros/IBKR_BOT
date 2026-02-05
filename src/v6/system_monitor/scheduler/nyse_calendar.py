"""
NYSE Trading Calendar Utility

Determines trading days and market hours for NYSE.
Handles holidays, early closes, and weekends.

Usage:
    from v6.system_monitor.scheduler.nyse_calendar import NYSECalendar

    cal = NYSECalendar()

    if cal.is_trading_day():
        print("Today is a trading day")

    if cal.is_market_open():
        print("Market is open now!")

    if cal.is_pre_market():
        print("Pre-market hours")
"""

from datetime import date, datetime, time, timedelta
from typing import Optional

import pandas as pd
from loguru import logger


class NYSECalendar:
    """
    NYSE trading calendar with holidays and market hours.

    **Trading Hours:**
    - Pre-Market: 4:00 AM - 9:30 AM ET
    - Regular Session: 9:30 AM - 4:00 PM ET
    - Post-Market: 4:00 PM - 8:00 PM ET

    **Holidays (2026):**
    - New Year's Day: January 1, 2026
    - MLK Day: January 19, 2026
    - Washington's Birthday: February 16, 2026
    - Good Friday: April 10, 2026
    - Memorial Day: May 25, 2026
    - Juneteenth: June 19, 2026
    - Independence Day: July 3, 2026 (observed)
    - Labor Day: September 7, 2026
    - Thanksgiving: November 26, 2026
    - Christmas: December 25, 2026
    """

    # Trading hours
    PRE_MARKET_OPEN = time(4, 0)      # 4:00 AM ET
    MARKET_OPEN = time(9, 30)         # 9:30 AM ET
    MARKET_CLOSE = time(16, 0)        # 4:00 PM ET
    POST_MARKET_CLOSE = time(20, 0)   # 8:00 PM ET

    # US Holidays 2026
    HOLIDAYS_2026 = [
        date(2026, 1, 1),   # New Year's Day
        date(2026, 1, 19),  # MLK Day
        date(2026, 2, 16),  # Washington's Birthday (observed)
        date(2026, 4, 10),  # Good Friday
        date(2026, 5, 25),  # Memorial Day
        date(2026, 6, 19),  # Juneteenth
        date(2026, 7, 3),   # Independence Day (observed)
        date(2026, 9, 7),   # Labor Day
        date(2026, 11, 26), # Thanksgiving
        date(2026, 12, 25),  # Christmas
    ]

    def __init__(self):
        """Initialize NYSE calendar."""
        self.current_year = date.today().year

    def is_trading_day(self, check_date: Optional[date] = None) -> bool:
        """
        Check if a date is a trading day.

        Args:
            check_date: Date to check (default: today)

        Returns:
            True if it's a trading day, False otherwise
        """
        if check_date is None:
            check_date = date.today()

        # Weekend
        if check_date.weekday() >= 5:  # Saturday = 5, Sunday = 6
            return False

        # Holiday
        if check_date in self.HOLIDAYS_2026:
            return False

        return True

    def is_market_open(self, check_time: Optional[datetime] = None) -> bool:
        """
        Check if market is currently open (9:30 AM - 4:00 PM ET).

        Args:
            check_time: Time to check (default: now)

        Returns:
            True if market is open, False otherwise
        """
        if check_time is None:
            check_time = datetime.now()

        check_date = check_time.date()

        # Must be a trading day
        if not self.is_trading_day(check_date):
            return False

        # Check if within market hours
        current_time = check_time.time()

        return self.MARKET_OPEN <= current_time <= self.MARKET_CLOSE

    def is_pre_market(self, check_time: Optional[datetime] = None) -> bool:
        """
        Check if in pre-market hours (4:00 AM - 9:30 AM ET).

        Args:
            check_time: Time to check (default: now)

        Returns:
            True if in pre-market, False otherwise
        """
        if check_time is None:
            check_time = datetime.now()

        check_date = check_time.date()

        # Must be a trading day
        if not self.is_trading_day(check_date):
            return False

        current_time = check_time.time()

        return self.PRE_MARKET_OPEN <= current_time < self.MARKET_OPEN

    def is_post_market(self, check_time: Optional[datetime] = None) -> bool:
        """
        Check if in post-market hours (4:00 PM - 8:00 PM ET).

        Args:
            check_time: Time to check (default: now)

        Returns:
            True if in post-market, False otherwise
        """
        if check_time is None:
            check_time = datetime.now()

        check_date = check_time.date()

        # Must be a trading day
        if not self.is_trading_day(check_date):
            return False

        current_time = check_time.time()

        return self.MARKET_CLOSE < current_time <= self.POST_MARKET_CLOSE

    def is_market_hours(self, check_time: Optional[datetime] = None) -> bool:
        """
        Check if within any market hours (pre-market through post-market).

        Args:
            check_time: Time to check (default: now)

        Returns:
            True if within market hours, False otherwise
        """
        if check_time is None:
            check_time = datetime.now()

        check_date = check_time.date()

        # Must be a trading day
        if not self.is_trading_day(check_date):
            return False

        current_time = check_time.time()

        return self.PRE_MARKET_OPEN <= current_time <= self.POST_MARKET_CLOSE

    def get_market_phase(self, check_time: Optional[datetime] = None) -> str:
        """
        Get current market phase.

        Args:
            check_time: Time to check (default: now)

        Returns:
            One of: 'closed', 'pre_market', 'market_open', 'post_market'
        """
        if check_time is None:
            check_time = datetime.now()

        check_date = check_time.date()

        # Check if trading day
        if not self.is_trading_day(check_date):
            return "closed"

        current_time = check_time.time()

        if self.PRE_MARKET_OPEN <= current_time < self.MARKET_OPEN:
            return "pre_market"
        elif self.MARKET_OPEN <= current_time <= self.MARKET_CLOSE:
            return "market_open"
        elif self.MARKET_CLOSE < current_time <= self.POST_MARKET_CLOSE:
            return "post_market"
        else:
            return "closed"

    def get_next_trading_day(self, check_date: Optional[date] = None) -> date:
        """
        Get the next trading day.

        Args:
            check_date: Starting date (default: today)

        Returns:
            Next trading day date
        """
        if check_date is None:
            check_date = date.today()

        next_date = check_date + timedelta(days=1)

        # Skip weekends and holidays
        while not self.is_trading_day(next_date):
            next_date += timedelta(days=1)

        return next_date

    def get_previous_trading_day(self, check_date: Optional[date] = None) -> date:
        """
        Get the previous trading day.

        Args:
            check_date: Starting date (default: today)

        Returns:
            Previous trading day date
        """
        if check_date is None:
            check_date = date.today()

        prev_date = check_date - timedelta(days=1)

        # Skip weekends and holidays
        while not self.is_trading_day(prev_date):
            prev_date -= timedelta(days=1)

        return prev_date


def main():
    """Test NYSE calendar."""
    cal = NYSECalendar()

    now = datetime.now()

    print("=" * 70)
    print("NYSE CALENDAR TEST")
    print("=" * 70)
    print(f"Current Time: {now}")
    print(f"Date: {now.date()}")
    print(f"Time: {now.time()}")
    print()
    print(f"Is Trading Day: {cal.is_trading_day()}")
    print(f"Market Phase: {cal.get_market_phase()}")
    print(f"Is Market Open: {cal.is_market_open()}")
    print(f"Is Pre-Market: {cal.is_pre_market()}")
    print(f"Is Post-Market: {cal.is_post_market()}")
    print(f"Is Market Hours: {cal.is_market_hours()}")
    print()
    print(f"Next Trading Day: {cal.get_next_trading_day()}")
    print(f"Previous Trading Day: {cal.get_previous_trading_day()}")


if __name__ == "__main__":
    main()
