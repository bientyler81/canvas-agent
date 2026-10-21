"""Two-way iMessage through an Inkbox agent identity on the free shared service (https://inkbox.ai)."""

from inkbox import Inkbox

# Keep each text a comfortable size; longer messages are split into parts.
MAX_TEXT_CHARS = 1500
HISTORY_TEXTS = 8


def split_message(body: str, limit: int = MAX_TEXT_CHARS) -> list[str]:
    """Split on line boundaries so no line is cut in half."""
    parts, current = [], ""
    for line in body.splitlines():
        if current and len(current) + len(line) + 1 > limit:
            parts.append(current)
            current = ""
        current = f"{current}\n{line}" if current else line[:limit]
    if current:
        parts.append(current)
    return parts


class Texter:
    def __init__(self, api_key: str, agent_handle: str):
        self.inkbox = Inkbox(api_key=api_key)
        self.identity = self.inkbox.get_identity(agent_handle)

    def send(self, to_number: str, body: str) -> list[str]:
        return [str(self.identity.send_imessage(to=to_number, text=part).id) for part in split_message(body)]

    def history(self, conversation_id: str, before_message_id: str) -> tuple[list[dict], bool]:
        """Recent conversation as chat turns (oldest first), excluding the triggering message.

        Also returns whether we've already replied after that message, so webhook retries
        don't produce duplicate answers.
        """
        msgs = sorted(self.identity.list_imessages(conversation_id=conversation_id, limit=HISTORY_TEXTS + 4),
                      key=lambda m: m.created_at)
        trigger = next((m for m in msgs if str(m.id) == before_message_id), None)
        already_replied = trigger is not None and any(
            m.direction == "outbound" and m.created_at > trigger.created_at for m in msgs
        )
        turns = [
            {"role": "user" if m.direction == "inbound" else "assistant", "content": m.content}
            for m in msgs
            if m.content and str(m.id) != before_message_id and (trigger is None or m.created_at < trigger.created_at)
        ]
        return turns[-HISTORY_TEXTS:], already_replied

    def close(self) -> None:
        self.inkbox.close()
