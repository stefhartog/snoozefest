from __future__ import annotations

from datetime import datetime, timedelta


def duration_to_speech(total_seconds: int | None) -> str:
    """Render a duration in a simple human-readable format for UI/voice."""
    if total_seconds is None:
        return ""

    seconds = max(0, int(total_seconds))
    if seconds == 0:
        return "now"

    days, rem = divmod(seconds, 24 * 3600)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)

    parts: list[str] = []
    if days:
        parts.append(f"{days} day" + ("s" if days != 1 else ""))
    if hours:
        parts.append(f"{hours} hour" + ("s" if hours != 1 else ""))
    if minutes:
        parts.append(f"{minutes} minute" + ("s" if minutes != 1 else ""))

    # Include seconds only for short durations to avoid noisy long phrases.
    if secs and not (days or hours):
        parts.append(f"{secs} second" + ("s" if secs != 1 else ""))

    return " ".join(parts) if parts else "now"


def remaining_to_day_phrase(total_seconds: int | None, now: datetime | None = None) -> str:
    """Render day reference from remaining seconds: today, tomorrow, or weekday."""
    if total_seconds is None:
        return ""

    seconds = max(0, int(total_seconds))
    now_dt = now or datetime.now()
    target_dt = now_dt + timedelta(seconds=seconds)

    today = now_dt.date()
    target = target_dt.date()
    if target == today:
        return "Today"
    if target == (today + timedelta(days=1)):
        return "Tomorrow"
    return target_dt.strftime("%A")
