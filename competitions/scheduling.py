from __future__ import annotations

from datetime import datetime, time

from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime


def parse_competition_start_at(value) -> datetime | None:
    """Parse YYYY-MM-DD or ISO datetime to start-of-day (UTC)."""
    if value is None or value == "":
        return None

    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        dt = parse_datetime(value)
        if dt is None:
            date = parse_date(value[:10])
            if date is None:
                return None
            dt = datetime.combine(date, time.min)
        else:
            dt = dt.replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        return None

    if timezone.is_naive(dt):
        return timezone.make_aware(dt, timezone.get_current_timezone())
    return dt.astimezone(timezone.get_current_timezone()).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
