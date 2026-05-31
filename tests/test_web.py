"""Chat web app tests (TestClient over the in-process FastAPI app).

Skipped automatically when the optional ``web`` extra (fastapi + httpx) is not
installed — e.g. the offline CI gate, which installs only the core tooling — so
the deterministic core suite stays green without the web dependencies.
"""

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")  # starlette's TestClient transport

from fastapi.testclient import TestClient

from salesflow import web


@pytest.fixture()
def client() -> TestClient:
    web._SESSIONS.clear()
    return TestClient(web.app)


def _start(client: TestClient) -> str:
    return client.post("/api/start").json()["session_id"]


def test_healthz(client: TestClient) -> None:
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_home_page_renders(client: TestClient) -> None:
    # Serves the built React SPA when present, else the vanilla fallback chat.
    r = client.get("/")
    assert r.status_code == 200
    assert "SalesFlow AI" in r.text


def test_start_returns_opening_and_session(client: TestClient) -> None:
    d = client.post("/api/start").json()
    assert d["session_id"]
    assert d["phase"] == "warmup"
    assert "tutoring" in d["reply"].lower()
    assert d["terminal"] is False


def test_pricing_question_is_grounded(client: TestClient) -> None:
    sid = _start(client)
    d = client.post(
        "/api/chat", json={"session_id": sid, "message": "How much does it cost?"}
    ).json()
    # Pricing comes from structured config, never generated.
    assert "pricing-config" in d["grounded_sources"]
    assert "$" in d["reply"]
    assert d["objection"] is None  # a price *question*, not a price *objection*


def test_human_request_escalates_and_is_terminal(client: TestClient) -> None:
    sid = _start(client)
    d = client.post(
        "/api/chat", json={"session_id": sid, "message": "Can I talk to a human?"}
    ).json()
    assert d["escalation"] == "explicit_request"
    assert d["phase"] == "escalation"
    assert d["terminal"] is True


def test_disqualifier_graceful_exit(client: TestClient) -> None:
    sid = _start(client)
    d = client.post(
        "/api/chat", json={"session_id": sid, "message": "Not interested, I have no kids."}
    ).json()
    assert d["phase"] == "graceful_exit"
    assert d["outcome"] == "graceful_exit"
    assert d["terminal"] is True


def test_unknown_session_404(client: TestClient) -> None:
    r = client.post("/api/chat", json={"session_id": "nope", "message": "hi"})
    assert r.status_code == 404
    assert "error" in r.json()


def test_chat_after_terminal_is_409(client: TestClient) -> None:
    sid = _start(client)
    client.post("/api/chat", json={"session_id": sid, "message": "Can I talk to a human?"})
    r = client.post("/api/chat", json={"session_id": sid, "message": "still there?"})
    assert r.status_code == 409


def test_api_kpis_shape(client: TestClient) -> None:
    d = client.get("/api/kpis?n_ab=40").json()
    assert d["agent_version"]
    assert d["kpis"] and isinstance(d["kpis"], dict)
    assert d["hallucination_rate"] == 0.0  # grounded by construction
    assert d["ab"]["best"]
    assert d["sample_transcript"]["redacted"] is True


def test_voice_status_reports_backend(client: TestClient) -> None:
    d = client.get("/api/voice/status").json()
    assert "available" in d and "tts" in d and "stt" in d


def test_status_reports_persona_llm_and_voice(client: TestClient) -> None:
    d = client.get("/api/status").json()
    assert d["agent_persona"] == "Vani"
    assert d["agent_version"] == "vani-v1.0.0"
    assert "backend" in d["llm"]
    assert "available" in d["voice"]
    assert d["live_calls_recorded"] >= 0


def test_ws_voice_text_loop_is_grounded(client: TestClient) -> None:
    with client.websocket_connect("/ws/voice") as ws:
        opening = ws.receive_json()
        assert opening["type"] == "reply"
        assert opening["phase"] == "warmup"
        ws.send_json({"type": "utterance", "text": "How much does it cost?"})
        reply = ws.receive_json()
        assert reply["type"] == "reply"
        assert reply["transcript"] == "How much does it cost?"
        assert "pricing-config" in reply["grounded_sources"]


def test_ws_voice_escalation_emits_ended(client: TestClient) -> None:
    with client.websocket_connect("/ws/voice") as ws:
        ws.receive_json()  # opening
        ws.send_json({"type": "utterance", "text": "Can I talk to a human?"})
        reply = ws.receive_json()
        assert reply["escalation"] == "explicit_request"
        ended = ws.receive_json()
        assert ended["type"] == "ended"
        assert ended["outcome"] == "escalated"


def test_ws_voice_abandoned_call_is_still_recorded(client: TestClient) -> None:
    """User report: dashboard showed 1 live call after 3 completed. Calls that
    end via the client closing the websocket (End call / New call before reaching
    a terminal phase) must still be captured so the user sees their real activity.
    """
    from salesflow import web as web_module

    before = len(web_module._LIVE_CALLS)
    with client.websocket_connect("/ws/voice") as ws:
        ws.receive_json()  # opening
        ws.send_json({"type": "utterance", "text": "Hi."})
        ws.receive_json()  # reply (call is mid-conversation, not terminal)
        # Client disconnects without going through to close.
    assert len(web_module._LIVE_CALLS) == before + 1, "abandoned call must be recorded"
    captured = web_module._LIVE_CALLS[-1]
    assert captured.turns, "abandoned call must carry its transcript"


def test_ws_voice_barge_is_acked(client: TestClient) -> None:
    with client.websocket_connect("/ws/voice") as ws:
        ws.receive_json()  # opening
        ws.send_json({"type": "barge"})
        assert ws.receive_json()["type"] == "barge_ack"
