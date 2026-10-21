"""Vercel serverless entry point.

GET  /api/digest   - called by Vercel Cron each morning; sends the digest text
POST /api/inbound  - called by Inkbox when you text the bot; replies with an answer
GET  /api/setup    - one-time Inkbox setup, opened in your browser with ?key=CRON_SECRET
"""

import hmac
import os
import sys

from flask import Flask, Response, request
from inkbox import verify_webhook

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from canvas_digest.config import Config  # noqa: E402
from canvas_digest.inkbox_setup import setup  # noqa: E402
from canvas_digest.jobs import handle_incoming_text, run_digest  # noqa: E402

app = Flask(__name__)


def _authorized() -> bool:
    """Vercel Cron sends "Authorization: Bearer $CRON_SECRET"; a browser can pass ?key=$CRON_SECRET."""
    secret = os.environ.get("CRON_SECRET", "")
    supplied = request.headers.get("Authorization", "").removeprefix("Bearer ") or request.args.get("key", "")
    return bool(secret) and hmac.compare_digest(supplied, secret)


def _text(body: str) -> Response:
    return Response(body, mimetype="text/plain")


@app.get("/api/digest")
def digest():
    if not _authorized():
        return Response("unauthorized", status=401)
    return _text("Sent:\n\n" + run_digest(Config.from_env()))


@app.get("/api/setup")
def inkbox_setup():
    if not _authorized():
        return Response("unauthorized: open this link with ?key=<your CRON_SECRET>", status=401)
    api_key = os.environ.get("INKBOX_API_KEY", "")
    if not api_key:
        return _text("Add INKBOX_API_KEY in Vercel's environment variables and redeploy first.")
    handle = os.environ.get("INKBOX_AGENT_HANDLE") or "canvas-digest"
    return _text(setup(api_key, handle, f"https://{request.host}", rotate_key=request.args.get("rotate") == "1"))


@app.post("/api/inbound")
def inbound():
    cfg = Config.from_env()
    raw = request.get_data()
    if not cfg.inkbox_signing_key or not verify_webhook(
        payload=raw, headers=dict(request.headers), secret=cfg.inkbox_signing_key
    ):
        return Response("invalid signature", status=403)
    return handle_incoming_text(cfg, raw)


@app.get("/api/health")
def health():
    return "ok"
