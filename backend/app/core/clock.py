"""Wall-clock time at the credit union (`LOCAL_TIMEZONE`).

The given conversation timestamps are naive local times (design §3.1), so replies are
written the same way; and "today" for a refund (BR-11) is the credit union's day, not
the server's (the server runs in UTC).
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo


class LocalClock:
    def __init__(self, timezone: str) -> None:
        self._zone = ZoneInfo(timezone)

    def now(self) -> datetime:
        """Naive local time, like every timestamp in `messages`."""
        return datetime.now(self._zone).replace(tzinfo=None)

    def today(self) -> date:
        return datetime.now(self._zone).date()
