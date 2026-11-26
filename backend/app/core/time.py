"""Time helpers. Mandi dates are Indian dates, so "today" is always computed in IST."""

from datetime import date, datetime, timedelta, timezone

# Fixed offset: India has no DST, and this avoids needing the tzdata package on Windows.
IST = timezone(timedelta(hours=5, minutes=30), name="IST")


def today_ist() -> date:
    return datetime.now(IST).date()
