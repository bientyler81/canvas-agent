"""The two jobs the bot runs: the morning digest and replying to an incoming text."""

import json
from datetime import datetime, timezone

from .agent import answer, summarize_digest
from .canvas import CanvasClient
from .config import Config
from .digest import bucket, render_plain
from .texting import Texter


def _normalize(number: str) -> str:
    return "".join(ch for ch in number if ch.isdigit() or ch == "+")


def _course_grades(canvas: CanvasClient) -> str:
    """Current course grades, so the LLM can weigh assignments in weaker classes more heavily."""
    lines = []
    for c in canvas.active_courses():
        score = next(iter(c.get("enrollments") or []), {}).get("computed_current_score")
        if score is not None:
            lines.append(f"- {c.get('course_code') or c['name']}: {score:g}%")
    return "\n\nCURRENT COURSE GRADES\n" + "\n".join(lines) if lines else ""


def run_digest(cfg: Config) -> str:
    now = datetime.now(timezone.utc)
    canvas = CanvasClient(cfg.canvas_base_url, cfg.canvas_token)
    buckets = bucket(canvas.all_assignments(), now, cfg.timezone, cfg.include_submitted)
    print(f"Found {len(buckets.today)} today, {len(buckets.week)} this week, {len(buckets.month)} this month")

    message = render_plain(buckets, now, cfg.timezone, month_limit=3)
    if cfg.openrouter_api_key:
        try:
            raw = render_plain(buckets, now, cfg.timezone) + _course_grades(canvas)
            message = summarize_digest(raw, cfg.openrouter_api_key, cfg.openrouter_model)
        except Exception as exc:  # never skip the text just because the LLM call failed
            print(f"warning: OpenRouter failed, sending plain digest: {exc}")
    message += "\n\n(Text me any question about your classes! - Prof. Penny)"

    if cfg.dry_run:
        print("DRY_RUN set; not sending.")
    else:
        texter = Texter(cfg.inkbox_api_key, cfg.inkbox_agent_handle)
        try:
            texter.send(cfg.my_phone_number, message)
        finally:
            texter.close()
    return message


def ask(cfg: Config, question: str, history: list[dict] | None = None) -> str:
    if not cfg.openrouter_api_key:
        raise SystemExit("OPENROUTER_API_KEY is required to answer questions")
    canvas = CanvasClient(cfg.canvas_base_url, cfg.canvas_token)
    return answer(question, history or [], canvas, cfg.timezone, cfg.openrouter_api_key, cfg.openrouter_model)


def handle_incoming_text(cfg: Config, raw_body: bytes) -> str:
    """Process an Inkbox imessage.received webhook (signature already verified). Returns a status string."""
    payload = json.loads(raw_body)
    if payload.get("event_type") != "imessage.received":
        return "ignored: not imessage.received"
    msg = payload["data"]["message"]
    if msg.get("is_group"):
        return "ignored: group message"
    sender = msg.get("remote_number") or ""
    question = (msg.get("content") or "").strip()
    # Only the owner may query their Canvas data; ignore everyone else silently.
    if _normalize(sender) != _normalize(cfg.my_phone_number):
        return "ignored: unknown sender"
    if not question:
        return "ignored: empty text"

    texter = Texter(cfg.inkbox_api_key, cfg.inkbox_agent_handle)
    try:
        history, already_replied = texter.history(msg["conversation_id"], msg["id"])
        if already_replied:
            return "ignored: already answered (webhook retry)"
        try:
            reply = ask(cfg, question, history)
        except Exception as exc:
            print(f"error answering: {exc}")
            reply = "Oops, I hit a snag looking that up, sweetie. Try me again in a minute?"
        texter.send(sender, reply)
    finally:
        texter.close()
    return "answered"
