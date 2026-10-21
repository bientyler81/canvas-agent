"""Canvas LMS REST API client: active courses and their assignments."""

import html
import re
from dataclasses import dataclass
from datetime import datetime

import requests


@dataclass(frozen=True)
class Assignment:
    id: int
    course_id: int
    course: str
    name: str
    due_at: datetime | None  # timezone-aware; None when the assignment has no due date
    points: float | None
    url: str
    submitted: bool  # for To Do notes: marked complete in the Canvas planner
    score: float | None = None
    kind: str = "assignment"  # or "todo" for the student's own Canvas To Do notes


def _parse_time(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


def _is_done(sub: dict) -> bool:
    """Whether the student has actually finished an assignment.

    "graded" alone isn't enough: some instructors pre-enter a 0 for every quiz before it opens,
    which Canvas reports as graded with no submission.
    """
    return (
        bool(sub.get("submitted_at"))
        or sub.get("workflow_state") in ("submitted", "pending_review")
        or bool(sub.get("excused"))
        or (sub.get("workflow_state") == "graded" and (sub.get("score") or 0) > 0)
    )


def html_to_text(value: str | None) -> str:
    text = re.sub(r"<(br|/p|/li|/div|/h\d)[^>]*>", "\n", value or "", flags=re.I)
    text = html.unescape(re.sub(r"<[^>]+>", "", text))
    return re.sub(r"\n\s*\n+", "\n\n", text).strip()


class CanvasClient:
    def __init__(self, base_url: str, token: str, timeout: float = 30):
        self.base_url = base_url
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"Bearer {token}"
        self._courses: list[dict] | None = None
        self._assignments: dict[int, list[Assignment]] = {}

    def _get(self, path: str, params: dict | None = None):
        resp = self.session.get(f"{self.base_url}/api/v1{path}", params=params, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def _get_paginated(self, path: str, params: dict) -> list[dict]:
        """Follow Canvas's Link-header pagination and return every item."""
        url = f"{self.base_url}/api/v1{path}"
        params = {**params, "per_page": 100}
        items: list[dict] = []
        while url:
            resp = self.session.get(url, params=params, timeout=self.timeout)
            resp.raise_for_status()
            items.extend(resp.json())
            url = resp.links.get("next", {}).get("url")
            params = None  # the "next" URL already carries the query string
        return items

    def active_courses(self) -> list[dict]:
        if self._courses is None:
            courses = self._get_paginated(
                "/courses",
                {"enrollment_state": "active", "state[]": "available", "include[]": "total_scores"},
            )
            # Courses the user can't access come back with only an id and access_restricted_by_date.
            self._courses = [c for c in courses if c.get("name") and not c.get("access_restricted_by_date")]
        return self._courses

    def course_assignments(self, course: dict) -> list[Assignment]:
        if course["id"] in self._assignments:
            return self._assignments[course["id"]]
        raw = self._get_paginated(
            f"/courses/{course['id']}/assignments",
            {"include[]": "submission", "order_by": "due_at"},
        )
        label = course.get("course_code") or course["name"]
        out = []
        for a in raw:
            if not a.get("published", True):
                continue
            sub = a.get("submission") or {}
            out.append(
                Assignment(
                    id=a["id"],
                    course_id=course["id"],
                    course=label,
                    name=a["name"],
                    due_at=_parse_time(a.get("due_at")),
                    points=a.get("points_possible"),
                    url=a.get("html_url", ""),
                    submitted=_is_done(sub),
                    score=sub.get("score"),
                )
            )
        self._assignments[course["id"]] = out
        return out

    def todo_notes(self) -> list[Assignment]:
        """The student's own To Do notes from the Canvas planner, shaped like assignments."""
        notes = self._get_paginated("/planner_notes", {})
        # Completion lives in planner overrides; plannable_type has been seen as both "planner_note" and "PlannerNote".
        done = {
            o.get("plannable_id")
            for o in self._get_paginated("/planner/overrides", {})
            if (o.get("plannable_type") or "").replace("_", "").lower() == "plannernote" and o.get("marked_complete")
        }
        codes = {c["id"]: c.get("course_code") or c["name"] for c in self.active_courses()}
        print(f"Found {len(notes)} To Do notes ({len(done)} marked complete)")
        return [
            Assignment(
                id=n["id"],
                course_id=n.get("course_id") or 0,
                course=f"To Do ({codes[n['course_id']]})" if n.get("course_id") in codes else "To Do",
                name=n.get("title") or "(untitled)",
                due_at=_parse_time(n.get("todo_date")),
                points=None,
                url="",
                submitted=n["id"] in done,
                kind="todo",
            )
            for n in notes
            if n.get("workflow_state", "active") == "active"
        ]

    def all_assignments(self) -> list[Assignment]:
        assignments: list[Assignment] = []
        for course in self.active_courses():
            try:
                assignments.extend(self.course_assignments(course))
            except requests.HTTPError as exc:
                # Some courses (e.g. tabs disabled) 403 on assignments; skip rather than fail.
                print(f"warning: skipping {course.get('name')}: {exc}")
        try:
            assignments.extend(self.todo_notes())
        except requests.HTTPError as exc:
            print(f"warning: skipping To Do notes: {exc}")
        return assignments

    def assignment_details(self, course_id: int, assignment_id: int) -> dict:
        return self._get(
            f"/courses/{course_id}/assignments/{assignment_id}", {"include[]": "submission"}
        )

    def announcements(self, course_ids: list[int], limit: int = 10) -> list[dict]:
        if not course_ids:
            return []
        params = [("context_codes[]", f"course_{cid}") for cid in course_ids] + [("per_page", limit)]
        return self._get("/announcements", params)
