"""Opt-in daily invitation drafts; no sending or background worker is started."""

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class ReminderPreference:
    enabled: bool
    timezone: str = "Australia/Sydney"
    hour: int = 17
    quiet_start: int = 21
    quiet_end: int = 8

    def __post_init__(self):
        ZoneInfo(self.timezone)
        if any(not 0 <= value <= 23 for value in (self.hour, self.quiet_start, self.quiet_end)):
            raise ValueError("Hours must be between 0 and 23")


INVITATIONS = (
    "Could you take a little time outside today—somewhere green, quiet or simply open to the sky?",
    "Would a little play with a pet, a favourite game or a playful moment fit your day?",
    "Is there someone you would enjoy catching up with? You could suggest a walk or dinner.",
    "If you have children in your care, would a park, skate park or small shared adventure suit today?",
    "What would help you stop, relax and enjoy a few unhurried moments today?",
    "Could you make space for something you love: music, a hobby, a laugh or a new experience?",
    "Would you enjoy planning an outing or a holiday that fits your time and budget?",
)


def daily_invitation(preference: ReminderPreference, at: datetime, *, last_local_date: str | None = None):
    if at.tzinfo is None:
        raise ValueError("Supply a timezone-aware time")
    local = at.astimezone(ZoneInfo(preference.timezone))
    hour = local.hour
    start, end = preference.quiet_start, preference.quiet_end
    quiet = (start <= hour < end) if start < end else (hour >= start or hour < end) if start > end else False
    if not preference.enabled or quiet or hour != preference.hour or last_local_date == local.date().isoformat():
        return None
    return {"local_date": local.date().isoformat(), "audience": "persy_internal",
            "draft": INVITATIONS[local.date().toordinal() % len(INVITATIONS)],
            "delivery_executed": False}
