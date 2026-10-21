"""Settings loaded from environment variables (set in the Vercel dashboard in production)."""

import os
from dataclasses import dataclass
from zoneinfo import ZoneInfo


def _require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"Missing required environment variable: {name}")
    return value


def _optional(name: str) -> str:
    return os.environ.get(name, "").strip()


@dataclass(frozen=True)
class Config:
    canvas_base_url: str
    canvas_token: str
    openrouter_api_key: str
    openrouter_model: str
    inkbox_api_key: str
    inkbox_agent_handle: str
    inkbox_signing_key: str
    my_phone_number: str  # E.164, e.g. +15551234567; the only number the bot texts or answers
    timezone: ZoneInfo
    include_submitted: bool
    dry_run: bool

    @classmethod
    def from_env(cls) -> "Config":
        dry_run = _optional("DRY_RUN").lower() in ("1", "true", "yes")
        # Texting credentials are only needed when actually sending.
        inkbox = _optional if dry_run else _require
        return cls(
            canvas_base_url=_require("CANVAS_BASE_URL").rstrip("/"),
            canvas_token=_require("CANVAS_API_TOKEN"),
            openrouter_api_key=_optional("OPENROUTER_API_KEY"),
            openrouter_model=_optional("OPENROUTER_MODEL") or "anthropic/claude-haiku-5.5",
            inkbox_api_key=inkbox("INKBOX_API_KEY"),
            inkbox_agent_handle=_optional("INKBOX_AGENT_HANDLE") or "canvas-digest",
            inkbox_signing_key=_optional("INKBOX_SIGNING_KEY"),
            my_phone_number=inkbox("MY_PHONE_NUMBER"),
            timezone=ZoneInfo(_optional("TIMEZONE") or "America/New_York"),
            include_submitted=_optional("INCLUDE_SUBMITTED").lower() in ("1", "true", "yes"),
            dry_run=dry_run,
        )
