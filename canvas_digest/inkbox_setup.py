"""One-time Inkbox setup: enable iMessage on the bot and send its incoming messages to this app."""

from inkbox import Inkbox


def setup(api_key: str, handle: str, app_url: str, rotate_key: bool = False) -> str:
    webhook_url = f"{app_url.rstrip('/')}/api/inbound"
    lines = []
    with Inkbox(api_key=api_key) as inkbox:
        if handle in {i.agent_handle for i in inkbox.list_identities()}:
            identity = inkbox.get_identity(handle)
            if not identity.imessage_enabled:
                identity.update(imessage_enabled=True)
            lines.append(f"Using existing Inkbox identity '{handle}'.")
        else:
            identity = inkbox.create_identity(handle, display_name="Canvas Agent", imessage_enabled=True)
            lines.append(f"Created Inkbox identity '{handle}' with iMessage enabled.")

        existing = inkbox.webhooks.subscriptions.list(agent_identity_id=identity.id)
        if not any(s.url == webhook_url and "imessage.received" in s.event_types for s in existing):
            inkbox.webhooks.subscriptions.create(
                agent_identity_id=identity.id, url=webhook_url, event_types=["imessage.received"]
            )
        lines.append(f"Incoming iMessages go to {webhook_url}")

        # The signing key is shown only once, so only make one when needed (or asked).
        if rotate_key or not identity.signing_key_configured:
            key = identity.create_signing_key().signing_key
            lines.append(
                "\nSTEP: In Vercel, add this environment variable, then redeploy:\n"
                f"  INKBOX_SIGNING_KEY = {key}"
            )
        else:
            lines.append("Signing key already exists (add ?rotate=1 to this link to make a new one).")

        # The shared router number can change, so always look it up rather than hardcoding it.
        router = inkbox.imessages.get_triage_number()

    lines.append(
        f"\nSTEP: From your iPhone, text exactly this:\n  {router.connect_command}\nto {router.number}\n"
        "The router replies to confirm and sends the bot's contact card. Then text the bot \"hi\" in that "
        "conversation. Until you reply once, the bot can only send short messages, so the full morning digest "
        "needs that first message."
    )
    return "\n".join(lines)
