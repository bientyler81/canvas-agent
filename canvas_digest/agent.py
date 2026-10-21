"""The Canvas agent: an OpenRouter model that answers questions by calling Canvas tools."""

import json
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .canvas import Assignment, CanvasClient, html_to_text
from .digest import relative_due
from .openrouter import chat

MAX_STEPS = 6

PERSONA = """You are Professor Penny, a sweet, bubbly professor who adores this student and dotes on them.
- Warm, encouraging and a little playful: call them things like "my star student" or "sweetie", cheer their progress, and fuss gently when a deadline is close ("don't stay up too late on this one, okay?").
- Sprinkle in an occasional cute emoji (like a heart, sparkle or apple), at most two per message.
- Keep it wholesome and caring, like a favorite teacher, never romantic or flirty.
- Personality never comes at the cost of accuracy or brevity: the facts come first, the charm wraps around them."""

DIGEST_PROMPT = PERSONA + """

You write the student's morning text message about their Canvas assignments.
Rules:
- Keep three sections in this order: "Due today", "This week", "This month". Never drop an assignment from today or this week.
- For "This month", if there are more than 8 items, list the 8 soonest and say "+N more".
- Each item: course code, short assignment name, and when it's due. Shorten long names sensibly.
- Say when things are due exactly as the input words it, relative to today ("tomorrow at 5PM", "next Thursday at 11:59PM"). Never turn it into a calendar date.
- Open with one short, sweet good-morning line in your voice (e.g. how heavy the day looks); flag anything due within the next few hours.
- Plain text only: no markdown. Stay under 1200 characters.
- Do not invent assignments, dates, or courses."""

CHAT_PROMPT = PERSONA + """

You answer the student's text messages, with read access to their Canvas LMS.
Right now it is {now} ({tz}).
- Use the tools to look things up; never guess assignment names, due dates, or grades.
- Match course references loosely ("bio", "calc 2", "the english class") against list_courses.
- Answer in plain text suitable for a text message: short, no markdown, under 600 characters unless the user asks for a full list.
- Say when things are due relative to today, using the tools' "due" wording as-is ("tomorrow at 5PM", "next Thursday at 11:59PM"). Only give the calendar date ("due_date") if the student asks for it.
- If something can't be found, say so briefly and suggest what you can look up instead."""

TOOLS = [
    {"type": "function", "function": {
        "name": "list_courses",
        "description": "List the student's active courses with id, name, code and current grade.",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "get_assignments",
        "description": "List assignments, optionally for one course, filtered by due-date window and/or name.",
        "parameters": {"type": "object", "properties": {
            "course_id": {"type": "integer", "description": "Limit to this course (from list_courses)."},
            "name_contains": {"type": "string", "description": "Case-insensitive text to match in the assignment name."},
            "days_ahead": {"type": "integer", "description": "Include items due up to this many days from now. Default 30."},
            "days_back": {"type": "integer", "description": "Include items due this many days in the past (for missing/late work). Default 0."},
            "include_undated": {"type": "boolean", "description": "Also include assignments with no due date. Default false."},
        }},
    }},
    {"type": "function", "function": {
        "name": "get_assignment_details",
        "description": "Full details of one assignment: instructions, points, submission status and score.",
        "parameters": {"type": "object", "properties": {
            "course_id": {"type": "integer"},
            "assignment_id": {"type": "integer"},
        }, "required": ["course_id", "assignment_id"]},
    }},
    {"type": "function", "function": {
        "name": "get_announcements",
        "description": "Recent course announcements, optionally for one course.",
        "parameters": {"type": "object", "properties": {"course_id": {"type": "integer"}}},
    }},
]


def _due_fields(dt: datetime | None, tz: ZoneInfo, now: datetime) -> dict:
    """Relative wording to say ("next Thursday at 11:59PM"), plus the calendar date if the student asks."""
    if dt is None:
        return {"due": "no due date", "due_date": None}
    return {"due": relative_due(dt, now, tz), "due_date": dt.astimezone(tz).strftime("%a %b %-d %Y")}


def _assignment_row(a: Assignment, tz: ZoneInfo, now: datetime) -> dict:
    return {
        "course_id": a.course_id, "assignment_id": a.id, "course": a.course, "name": a.name,
        **_due_fields(a.due_at, tz, now), "points": a.points, "submitted": a.submitted, "score": a.score,
    }


class CanvasTools:
    """Executes tool calls against Canvas and returns JSON-serializable results."""

    def __init__(self, canvas: CanvasClient, tz: ZoneInfo, now: datetime):
        self.canvas, self.tz, self.now = canvas, tz, now

    def list_courses(self) -> list[dict]:
        out = []
        for c in self.canvas.active_courses():
            enrollment = next(iter(c.get("enrollments") or []), {})
            out.append({
                "course_id": c["id"], "name": c["name"], "code": c.get("course_code"),
                "current_grade": enrollment.get("computed_current_grade"),
                "current_score": enrollment.get("computed_current_score"),
            })
        return out

    def get_assignments(self, course_id: int | None = None, name_contains: str | None = None,
                        days_ahead: int = 30, days_back: int = 0, include_undated: bool = False) -> list[dict]:
        if course_id is not None:
            course = next((c for c in self.canvas.active_courses() if c["id"] == course_id), None)
            if course is None:
                return [{"error": f"No active course with id {course_id}"}]
            items = self.canvas.course_assignments(course)
        else:
            items = self.canvas.all_assignments()
        start = self.now - timedelta(days=days_back)
        end = self.now + timedelta(days=days_ahead)
        needle = (name_contains or "").lower()
        rows = []
        for a in items:
            if needle and needle not in a.name.lower():
                continue
            if a.due_at is None:
                if include_undated or needle:
                    rows.append(a)
            elif needle or start <= a.due_at <= end:
                rows.append(a)
        rows.sort(key=lambda a: a.due_at or datetime.max.replace(tzinfo=timezone.utc))
        return [_assignment_row(a, self.tz, self.now) for a in rows[:60]]

    def get_assignment_details(self, course_id: int, assignment_id: int) -> dict:
        a = self.canvas.assignment_details(course_id, assignment_id)
        sub = a.get("submission") or {}
        due = a.get("due_at")
        return {
            "name": a["name"],
            **_due_fields(datetime.fromisoformat(due.replace("Z", "+00:00")) if due else None, self.tz, self.now),
            "points": a.get("points_possible"),
            "submission_types": a.get("submission_types"),
            "instructions": html_to_text(a.get("description"))[:2000],
            "submitted": bool(sub.get("submitted_at")),
            "score": sub.get("score"),
            "late": sub.get("late"), "missing": sub.get("missing"),
            "url": a.get("html_url"),
        }

    def get_announcements(self, course_id: int | None = None) -> list[dict]:
        ids = [course_id] if course_id else [c["id"] for c in self.canvas.active_courses()]
        return [
            {"title": n.get("title"), "posted": n.get("posted_at"), "message": html_to_text(n.get("message"))[:600]}
            for n in self.canvas.announcements(ids)
        ]

    def call(self, name: str, arguments: str) -> str:
        try:
            fn = getattr(self, name) if name in {t["function"]["name"] for t in TOOLS} else None
            if fn is None:
                return json.dumps({"error": f"unknown tool {name}"})
            return json.dumps(fn(**json.loads(arguments or "{}")), default=str)
        except Exception as exc:  # report tool errors back to the model instead of crashing
            return json.dumps({"error": str(exc)})


def answer(question: str, history: list[dict], canvas: CanvasClient, tz: ZoneInfo,
           api_key: str, model: str, now: datetime | None = None) -> str:
    """Answer a texted question. `history` is prior turns as {"role", "content"} dicts, oldest first."""
    now = now or datetime.now(timezone.utc)
    tools = CanvasTools(canvas, tz, now)
    local_now = now.astimezone(tz).strftime("%A, %B %-d %Y, %-I:%M %p")
    messages = [{"role": "system", "content": CHAT_PROMPT.format(now=local_now, tz=tz.key)},
                *history, {"role": "user", "content": question}]
    for _ in range(MAX_STEPS):
        msg = chat(messages, api_key, model, tools=TOOLS)
        calls = msg.get("tool_calls") or []
        if not calls:
            return (msg.get("content") or "").strip() or "Oh no, I couldn't come up with an answer, sweetie. Try asking me another way?"
        messages.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": calls})
        for call in calls:
            fn = call["function"]
            messages.append({"role": "tool", "tool_call_id": call["id"],
                             "content": tools.call(fn["name"], fn.get("arguments", "{}"))})
    return "Goodness, that one had me digging through too many files! Ask me about one class or assignment at a time?"


def summarize_digest(raw_digest: str, api_key: str, model: str) -> str:
    msg = chat([{"role": "system", "content": DIGEST_PROMPT}, {"role": "user", "content": raw_digest}],
               api_key, model, max_tokens=600)
    text = (msg.get("content") or "").strip()
    if not text:
        raise ValueError("OpenRouter returned an empty message")
    return text
