"""Group assignments into today / this week / this month and render a plain-text digest."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .canvas import Assignment


@dataclass
class Buckets:
    today: list[Assignment] = field(default_factory=list)
    week: list[Assignment] = field(default_factory=list)   # tomorrow through day 7
    month: list[Assignment] = field(default_factory=list)  # day 8 through day 30


def bucket(assignments: list[Assignment], now: datetime, tz: ZoneInfo,
           include_submitted: bool = False) -> Buckets:
    start_of_today = now.astimezone(tz).replace(hour=0, minute=0, second=0, microsecond=0)
    end_today = start_of_today + timedelta(days=1)
    end_week = start_of_today + timedelta(days=7)
    end_month = start_of_today + timedelta(days=30)

    b = Buckets()
    for a in sorted((a for a in assignments if a.due_at), key=lambda x: x.due_at):
        if a.submitted and not include_submitted:
            continue
        due = a.due_at.astimezone(tz)
        if due < now:  # already past due (including earlier today)
            continue
        if due < end_today:
            b.today.append(a)
        elif due < end_week:
            b.week.append(a)
        elif due < end_month:
            b.month.append(a)
    return b


def _line(a: Assignment, tz: ZoneInfo, with_day: bool) -> str:
    due = a.due_at.astimezone(tz)
    when = due.strftime("%a %-m/%-d %-I:%M%p" if with_day else "%-I:%M%p").replace(":00", "")
    return f"- {a.course}: {a.name} ({when})"


def render_plain(b: Buckets, now: datetime, tz: ZoneInfo) -> str:
    """Deterministic digest used as LLM input and as the fallback SMS."""
    parts = [f"Canvas digest for {now.astimezone(tz).strftime('%A, %b %-d')}"]
    sections = [
        ("DUE TODAY", b.today, False),
        ("DUE THIS WEEK", b.week, True),
        ("DUE THIS MONTH", b.month, True),
    ]
    for title, items, with_day in sections:
        parts.append(f"\n{title} ({len(items)})")
        parts.extend([_line(a, tz, with_day) for a in items] or ["- Nothing"])
    return "\n".join(parts)
