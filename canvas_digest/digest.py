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


def relative_due(due: datetime, now: datetime, tz: ZoneInfo) -> str:
    """When something is due, relative to now: "today at 5PM", "this Friday at 11:59PM", "next Thursday at 9AM"."""
    due, today = due.astimezone(tz), now.astimezone(tz).date()
    days = (due.date() - today).days
    # Calendar weeks (Monday start) between this week and the due date's week.
    weeks = ((due.date() - timedelta(days=due.weekday())) - (today - timedelta(days=today.weekday()))).days // 7
    weekday = due.strftime("%A")
    if days == 0:
        day = "today"
    elif days == 1:
        day = "tomorrow"
    elif days == -1:
        day = "yesterday"
    elif days < 0:
        day = f"{-days} days ago"
    elif weeks == 0:
        day = f"this {weekday}"
    elif weeks == 1:
        day = f"next {weekday}"
    else:
        day = f"{weekday}, {weeks} weeks from now"
    return f"{day} at {due.strftime('%-I:%M%p').replace(':00', '')}"


def _line(a: Assignment, now: datetime, tz: ZoneInfo) -> str:
    return f"- {a.course}: {a.name} (due {relative_due(a.due_at, now, tz)})"


def render_plain(b: Buckets, now: datetime, tz: ZoneInfo) -> str:
    """Deterministic digest used as LLM input and as the fallback SMS."""
    parts = [f"Canvas digest for {now.astimezone(tz).strftime('%A, %b %-d')}"]
    sections = [
        ("DUE TODAY", b.today),
        ("DUE THIS WEEK", b.week),
        ("DUE THIS MONTH", b.month),
    ]
    for title, items in sections:
        parts.append(f"\n{title} ({len(items)})")
        parts.extend([_line(a, now, tz) for a in items] or ["- Nothing"])
    return "\n".join(parts)
