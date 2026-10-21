import json
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from canvas_digest import agent
from canvas_digest.canvas import Assignment

TZ = ZoneInfo("America/New_York")
NOW = datetime(2026, 10, 21, 11, 0, tzinfo=timezone.utc)
COURSES = [{"id": 7, "name": "Intro Biology", "course_code": "BIO101",
            "enrollments": [{"computed_current_grade": "A-", "computed_current_score": 91.2}]}]
LAB = Assignment(42, 7, "BIO101", "Lab Report 4", NOW + timedelta(days=2), 20, "u", False)
OLD = Assignment(41, 7, "BIO101", "Lab Report 3", NOW - timedelta(days=5), 20, "u", True, 18)


class FakeCanvas:
    def active_courses(self): return COURSES
    def course_assignments(self, course): return [OLD, LAB]
    def all_assignments(self): return [OLD, LAB]


def test_get_assignments_filters():
    tools = agent.CanvasTools(FakeCanvas(), TZ, NOW)
    upcoming = tools.get_assignments(course_id=7)
    assert [r["name"] for r in upcoming] == ["Lab Report 4"]
    assert upcoming[0]["due"] == "this Friday at 7AM"
    assert upcoming[0]["due_date"] == "Fri Oct 23 2026"
    by_name = tools.get_assignments(name_contains="lab report")  # name search ignores the date window
    assert [r["name"] for r in by_name] == ["Lab Report 3", "Lab Report 4"]
    assert tools.list_courses()[0]["current_grade"] == "A-"
    assert "error" in json.loads(tools.call("get_assignments", '{"course_id": 999}'))[0]


def test_answer_runs_tool_loop(monkeypatch):
    replies = iter([
        {"tool_calls": [{"id": "c1", "type": "function",
                         "function": {"name": "get_assignments", "arguments": '{"name_contains": "lab report 4"}'}}]},
        {"content": "BIO101 Lab Report 4 is due Fri Oct 23 at 7 AM."},
    ])
    seen = []

    def fake_chat(messages, api_key, model, tools=None, **kw):
        seen.append(list(messages))
        return next(replies)

    monkeypatch.setattr(agent, "chat", fake_chat)
    out = agent.answer("when is lab report 4 due?", [{"role": "user", "content": "hi"}],
                       FakeCanvas(), TZ, "key", "model", now=NOW)
    assert out == "BIO101 Lab Report 4 is due Fri Oct 23 at 7 AM."
    second_call = seen[1]
    assert second_call[1] == {"role": "user", "content": "hi"}  # history passed through
    assert second_call[-1]["role"] == "tool" and "Lab Report 4" in second_call[-1]["content"]
    assert "Wednesday, October 21 2026" in second_call[0]["content"]
