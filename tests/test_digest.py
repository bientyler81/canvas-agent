from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from canvas_digest.canvas import Assignment
from canvas_digest.digest import bucket, render_plain
from canvas_digest.texting import split_message

TZ = ZoneInfo("America/New_York")
NOW = datetime(2026, 10, 21, 11, 0, tzinfo=timezone.utc)  # 7 AM Eastern


def make(name, delta, submitted=False):
    due = NOW + delta if delta is not None else None
    return Assignment(1, 1, "BIO101", name, due, 10, "", submitted)


def test_bucketing():
    items = [
        make("past", timedelta(hours=-1)),
        make("tonight", timedelta(hours=15)),
        make("tomorrow", timedelta(days=1)),
        make("day6", timedelta(days=6)),
        make("day10", timedelta(days=10)),
        make("day40", timedelta(days=40)),
        make("undated", None),
        make("done", timedelta(hours=5), submitted=True),
    ]
    b = bucket(items, NOW, TZ)
    assert [a.name for a in b.today] == ["tonight"]
    assert [a.name for a in b.week] == ["tomorrow", "day6"]
    assert [a.name for a in b.month] == ["day10"]

    with_submitted = bucket(items, NOW, TZ, include_submitted=True)
    assert [a.name for a in with_submitted.today] == ["done", "tonight"]


def test_render_plain_empty_sections():
    text = render_plain(bucket([], NOW, TZ), NOW, TZ)
    assert "Wednesday, Oct 21" in text
    assert text.count("- Nothing") == 3


def test_split_message_keeps_lines_whole():
    body = "\n".join(f"line {i} " + "x" * 50 for i in range(60))
    parts = split_message(body, limit=500)
    assert all(len(p) <= 500 for p in parts)
    assert "\n".join(parts) == body
