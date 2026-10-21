import hashlib
import hmac
import json

import pytest

ENV = {
    "CANVAS_BASE_URL": "https://canvas.example.edu", "CANVAS_API_TOKEN": "t",
    "OPENROUTER_API_KEY": "k", "INKBOX_API_KEY": "ik", "INKBOX_SIGNING_KEY": "whsec_abc",
    "MY_PHONE_NUMBER": "+15551234567", "CRON_SECRET": "cron123",
}


@pytest.fixture
def env(monkeypatch):
    for k, v in ENV.items():
        monkeypatch.setenv(k, v)


class FakeTexter:
    sent = []
    replied = False

    def __init__(self, *a): pass
    def history(self, conversation_id, message_id): return [{"role": "assistant", "content": "earlier"}], FakeTexter.replied
    def send(self, to, body): FakeTexter.sent.append((to, body))
    def close(self): pass


def payload(sender="+15551234567", text="what's due in bio?", is_group=False):
    return json.dumps({"id": "evt_1", "event_type": "imessage.received", "timestamp": "x", "data": {
        "message": {"id": "msg_1", "conversation_id": "conv_1", "direction": "inbound",
                    "remote_number": sender, "content": text, "is_group": is_group},
        "reaction": None, "contacts": [], "agent_identities": []}}).encode()


def signed(body, key="abc"):
    sig = hmac.new(key.encode(), b"req1.123." + body, hashlib.sha256).hexdigest()
    return {"x-inkbox-signature": f"sha256={sig}", "x-inkbox-request-id": "req1",
            "x-inkbox-timestamp": "123", "content-type": "application/json"}


@pytest.fixture
def client(env, monkeypatch):
    from canvas_digest import jobs
    FakeTexter.sent, FakeTexter.replied = [], False
    monkeypatch.setattr(jobs, "Texter", FakeTexter)
    monkeypatch.setattr(jobs, "ask", lambda cfg, q, h: f"answer to {q} (history {len(h)})")
    from api.index import app
    return app.test_client()


def test_inbound_answers_owner(client):
    body = payload()
    r = client.post("/api/inbound", data=body, headers=signed(body))
    assert r.status_code == 200 and r.text == "answered"
    assert FakeTexter.sent == [("+15551234567", "answer to what's due in bio? (history 1)")]


def test_inbound_rejects_bad_signature(client):
    body = payload()
    r = client.post("/api/inbound", data=body, headers=signed(body, key="wrong"))
    assert r.status_code == 403 and FakeTexter.sent == []


def test_inbound_ignores_strangers_and_retries(client):
    body = payload(sender="+19998887777")
    assert client.post("/api/inbound", data=body, headers=signed(body)).text == "ignored: unknown sender"
    body = payload(is_group=True)
    assert client.post("/api/inbound", data=body, headers=signed(body)).text == "ignored: group message"
    FakeTexter.replied = True
    body = payload()
    assert "already answered" in client.post("/api/inbound", data=body, headers=signed(body)).text
    assert FakeTexter.sent == []


def test_digest_requires_cron_secret(client, monkeypatch):
    from api import index
    monkeypatch.setattr(index, "run_digest", lambda cfg: "msg")
    assert client.get("/api/digest").status_code == 401
    r = client.get("/api/digest", headers={"Authorization": "Bearer cron123"})
    assert r.status_code == 200 and r.text.endswith("msg")
    assert client.get("/api/digest?key=cron123").status_code == 200
    assert client.get("/api/digest?key=wrong").status_code == 401
    assert client.get("/api/setup").status_code == 401
