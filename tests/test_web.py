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
    r = client.get("/")
    assert r.status_code == 200
    assert "talk to Alex" in r.text
    assert "/api/chat" in r.text  # the page wires the JSON API


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
