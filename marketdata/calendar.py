"""NYSE regular sessions, including actual holiday and early-close schedules."""
from datetime import datetime
from functools import lru_cache
from zoneinfo import ZoneInfo

import pandas_market_calendars as mcal


class USMarketCalendar:
    def __init__(self):
        self._calendar = mcal.get_calendar("NYSE")

    @lru_cache(maxsize=32)
    def _session(self, date):
        return self._calendar.schedule(start_date=date, end_date=date)

    def is_open(self, now: datetime) -> bool:
        if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("Market calendar requires a timezone-aware datetime")
        date = now.astimezone(ZoneInfo("America/New_York")).date()
        schedule = self._session(date)
        if schedule.empty:
            return False
        row = schedule.iloc[0]
        return bool(row["market_open"] <= now < row["market_close"])

    def require_open(self, now: datetime) -> None:
        if not self.is_open(now):
            raise ValueError("US regular stock market session is closed")
