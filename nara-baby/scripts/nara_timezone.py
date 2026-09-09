"""Timezone adapter for the reviewed upstream NaraAPI (no login on import)."""

import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

def resolve_timezone(name=None):
    """Explicit setting, then NARA_TIMEZONE, then configured user preference."""
    from nara_config import load_config
    selected = name if name is not None else os.environ.get("NARA_TIMEZONE") or load_config().get("timezone")
    if not selected:
        raise ValueError("Choose a timezone during Nara onboarding before creating activities.")
    return ZoneInfo(selected)  # Fail before authentication on an invalid setting.


def epoch_ms(value, timezone_name=None, *, fold=None):
    """Convert an ISO datetime; reject nonexistent/ambiguous local times.

    An explicit UTC offset identifies an instant. A naive datetime uses the
    configured zone. For a repeated hour, fold=0/1 selects first/second occurrence.
    """
    # Python 3.10 requires an explicit offset for the ISO UTC suffix.
    if isinstance(value, str) and value.endswith('Z'):
        value = value[:-1] + '+00:00'
    dt = datetime.fromisoformat(value) if isinstance(value, str) else value
    if not isinstance(dt, datetime):
        raise TypeError("Expected an ISO datetime or datetime object")
    if fold not in (None, 0, 1):
        raise ValueError("fold must be 0 or 1")
    if dt.tzinfo is not None and dt.utcoffset() is not None:
        return int(dt.timestamp() * 1000)
    zone = resolve_timezone(timezone_name)
    candidates = {}
    for choice in (0, 1):
        aware = dt.replace(tzinfo=zone, fold=choice)
        back = aware.astimezone(timezone.utc).astimezone(zone)
        if back.replace(tzinfo=None) == dt:
            candidates[choice] = aware
    if not candidates:
        raise ValueError("This local time does not exist due to a daylight-saving transition")
    if fold is not None:
        if fold not in candidates:
            raise ValueError("Invalid occurrence for this local time")
        return int(candidates[fold].timestamp() * 1000)
    instants = {item.timestamp() for item in candidates.values()}
    if len(instants) > 1:
        raise ValueError("This local time is ambiguous; specify an offset or fold=0/1")
    return int(next(iter(instants)) * 1000)


def timezone_client(base_class):
    """Wrap NaraAPI so all helper-created records share a validated timezone.

    This adapter fixes timezone handling only; it does not change authentication,
    request retry, child discovery, or upstream numeric encodings.
    """
    class TimezoneNaraAPI(base_class):
        def __init__(self, email, password, *, timezone_name=None):
            self.activity_timezone = resolve_timezone(timezone_name).key
            super().__init__(email=email, password=password)

        def log_activity(self, track_type, begin_dt=None, end_dt=None, track_id=None, **kwargs):
            # All upstream manual loggers and timer starts dispatch here, even
            # methods (growth, health, timers) without **kwargs in their signature.
            selected = kwargs.pop("tz", self.activity_timezone)
            kwargs["tz"] = resolve_timezone(selected).key
            return super().log_activity(
                track_type, begin_dt=begin_dt, end_dt=end_dt,
                track_id=track_id, **kwargs
            )

    return TimezoneNaraAPI
