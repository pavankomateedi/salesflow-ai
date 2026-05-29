"""FastAPI backend for SalesFlow AI.

Serves three things:
  * JSON APIs the React UI consumes — ``/api/start`` + ``/api/chat`` (text chat),
    ``/api/kpis`` (observability dashboard data), ``/api/voice/status``.
  * ``/ws/voice`` — a WebSocket voice loop: prospect audio (or recognised text)
    -> STT -> deterministic agent -> TTS audio back, with barge-in. Cartesia
    powers STT+TTS when ``CARTESIA_API_KEY`` is set; offline it runs the mock
    backend (text replies, no synthesised audio) so the loop is testable.
  * The built React SPA (``frontend/dist``) at ``/``; if no build is present
    (CI, bare checkout) it falls back to a self-contained vanilla chat page.

The conversation engine is the deterministic offline core — pricing is grounded
from config, policy/competitive answers are retrieval-only — so the whole thing
runs with no API key; OpenAI/Cartesia only upgrade phrasing and voice.
"""

from __future__ import annotations

import base64
import os
import uuid
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from salesflow import AGENT_VERSION
from salesflow.agent.agent import AgentAction, SalesAgent
from salesflow.domain.models import ConversationState, Lead
from salesflow.eval.dashboard import build_dashboard
from salesflow.voice.factory import get_stt, get_tts, voice_available
from salesflow.voice.interfaces import AudioChunk

app = FastAPI(title="SalesFlow AI — Alex", version=AGENT_VERSION)

_agent = SalesAgent()
_SESSIONS: dict[str, ConversationState] = {}

_DEFAULT_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
_FRONTEND_DIST = Path(os.environ.get("SALESFLOW_FRONTEND_DIST", str(_DEFAULT_DIST)))
if (_FRONTEND_DIST / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=_FRONTEND_DIST / "assets"), name="assets")


class ChatRequest(BaseModel):
    session_id: str
    message: str


def _new_phone() -> str:
    return "+1" + uuid.uuid4().hex[:10]


def _payload(state: ConversationState, action: AgentAction) -> dict[str, object]:
    return {
        "reply": action.utterance,
        "phase": action.phase.value,
        "outcome": state.outcome.value,
        "asked_field": action.asked_field,
        "objection": action.objection.value if action.objection else None,
        "escalation": action.escalation.value if action.escalation else None,
        "grounded_sources": action.grounded_sources,
        "decision": action.decision,
        "terminal": state.phase.is_terminal,
    }


# --- JSON API --------------------------------------------------------------


@app.get("/healthz")
def healthz() -> JSONResponse:
    return JSONResponse({"status": "ok", "version": AGENT_VERSION})


@app.post("/api/start")
def start() -> JSONResponse:
    session_id = uuid.uuid4().hex
    state = ConversationState(lead=Lead(phone=_new_phone()))
    _SESSIONS[session_id] = state
    payload = _payload(state, _agent.open(state))
    payload["session_id"] = session_id
    return JSONResponse(payload)


@app.post("/api/chat")
def chat(req: ChatRequest) -> JSONResponse:
    state = _SESSIONS.get(req.session_id)
    if state is None:
        return JSONResponse(
            {"error": "unknown or expired session — start a new call"}, status_code=404
        )
    if state.phase.is_terminal:
        return JSONResponse(
            {"error": "this call has ended — start a new one", "terminal": True}, status_code=409
        )
    return JSONResponse(_payload(state, _agent.respond(state, req.message)))


@lru_cache(maxsize=4)
def _kpis(n_ab: int) -> dict[str, object]:
    return build_dashboard(n_ab=n_ab)


@app.get("/api/kpis")
def api_kpis(n_ab: int = 200) -> JSONResponse:
    return JSONResponse(_kpis(max(20, min(2000, n_ab))))


@app.get("/api/voice/status")
def voice_status() -> JSONResponse:
    return JSONResponse(
        {
            "available": voice_available(),
            "stt": os.environ.get("SALESFLOW_STT", "mock") if voice_available() else "mock",
            "tts": "cartesia" if voice_available() else "mock",
            "note": (
                "Cartesia voice active."
                if voice_available()
                else "Set CARTESIA_API_KEY for live audio; text replies still work."
            ),
        }
    )


# --- WebSocket voice loop --------------------------------------------------


async def _send_audio(ws: WebSocket, text: str) -> None:
    """Synthesise and stream TTS audio (no-op when the mock backend has no PCM)."""
    try:
        audio: AudioChunk = get_tts().synthesize(text)
    except Exception as exc:  # live backend misconfigured — keep the text loop alive
        await ws.send_json({"type": "audio_error", "detail": str(exc)})
        return
    if audio.pcm:
        await ws.send_json(
            {"type": "audio", "b64": base64.b64encode(audio.pcm).decode(), "sample_rate": 16000}
        )


@app.websocket("/ws/voice")
async def ws_voice(ws: WebSocket) -> None:
    await ws.accept()
    state = ConversationState(lead=Lead(phone=_new_phone()))
    opening = _agent.open(state)
    await ws.send_json({"type": "reply", "transcript": None, **_payload(state, opening)})
    await _send_audio(ws, opening.utterance)

    try:
        while True:
            msg = await ws.receive_json()
            kind = msg.get("type")
            if kind == "barge":
                # Prospect spoke over the agent — client stops playback; ack it.
                await ws.send_json({"type": "barge_ack"})
                continue
            if kind == "end":
                break

            text = msg.get("text") or ""
            if not text and msg.get("audio_b64"):
                pcm = base64.b64decode(msg["audio_b64"])
                text = get_stt().transcribe(AudioChunk(duration_ms=0, pcm=pcm)).text
            if not text.strip():
                continue
            if state.phase.is_terminal:
                await ws.send_json({"type": "ended", "outcome": state.outcome.value})
                break

            action = _agent.respond(state, text)
            await ws.send_json({"type": "reply", "transcript": text, **_payload(state, action)})
            await _send_audio(ws, action.utterance)
            if state.phase.is_terminal:
                await ws.send_json({"type": "ended", "outcome": state.outcome.value})
                break
    except WebSocketDisconnect:
        pass


# --- React SPA (with vanilla fallback when unbuilt) ------------------------


def _spa_or_fallback() -> str:
    index = _FRONTEND_DIST / "index.html"
    if index.is_file():
        return index.read_text(encoding="utf-8")
    return _FALLBACK_PAGE


@app.get("/", response_class=HTMLResponse)
def home() -> HTMLResponse:
    return HTMLResponse(_spa_or_fallback())


@app.get("/voice", response_class=HTMLResponse)
def voice_page() -> HTMLResponse:
    return HTMLResponse(_spa_or_fallback())


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard_page() -> HTMLResponse:
    return HTMLResponse(_spa_or_fallback())


def main() -> None:  # pragma: no cover - thin uvicorn launcher
    import uvicorn

    uvicorn.run("salesflow.web:app", host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))


# --- vanilla fallback chat (served only when the React build is absent) ----

_FALLBACK_PAGE = (
    "<!doctype html><html lang=en><head><meta charset=utf-8>"
    "<meta name=viewport content='width=device-width,initial-scale=1'>"
    "<title>SalesFlow AI — Alex</title>"
    "<style>body{margin:0;background:#0f1419;color:#e6edf3;font:15px/1.5 system-ui,"
    "sans-serif}.wrap{max-width:720px;margin:0 auto;padding:32px 20px}"
    "h1{font-size:24px}a{color:#58a6ff}.log{border:1px solid #2a3441;background:#1a212b;"
    "border-radius:12px;padding:16px;height:52vh;overflow-y:auto;display:flex;"
    "flex-direction:column;gap:10px;margin:16px 0}.msg{max-width:80%;padding:10px 14px;"
    "border-radius:14px;white-space:pre-wrap}.agent{align-self:flex-start;background:#1f2a37}"
    ".you{align-self:flex-end;background:rgba(88,166,255,.16)}form{display:flex;gap:10px}"
    "input{flex:1;padding:12px;border-radius:10px;border:1px solid #2a3441;background:#0d1117;"
    "color:#e6edf3}button{padding:10px 16px;border-radius:10px;border:1px solid #2a3441;"
    "background:#22303f;color:#e6edf3;font-weight:600;cursor:pointer}</style></head>"
    "<body><div class=wrap><h1>SalesFlow AI — talk to Alex</h1>"
    "<p>React UI not built — serving the lightweight fallback chat. "
    "Build the SPA for the voice + dashboard experience: "
    "<code>cd frontend && npm install && npm run build</code>.</p>"
    "<div id=log class=log></div>"
    "<form id=f><input id=m autocomplete=off placeholder='Type what the parent says…'>"
    "<button>Send</button></form></div><script>"
    "const log=document.getElementById('log'),f=document.getElementById('f'),"
    "m=document.getElementById('m');let sid=null,done=false;"
    "function b(r,t){const d=document.createElement('div');d.className='msg '+r;"
    "d.textContent=t;log.appendChild(d);log.scrollTop=log.scrollHeight;}"
    "async function start(){const r=await fetch('/api/start',{method:'POST'});"
    "const d=await r.json();sid=d.session_id;b('agent',d.reply);}"
    "f.addEventListener('submit',async e=>{e.preventDefault();const t=m.value.trim();"
    "if(!t||done)return;b('you',t);m.value='';"
    "const r=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},"
    "body:JSON.stringify({session_id:sid,message:t})});const d=await r.json();"
    "if(d.error){b('agent',d.error);return;}b('agent',d.reply);"
    "if(d.terminal){done=true;b('agent','(call ended: '+d.outcome+')');}});start();"
    "</script></body></html>"
)


if __name__ == "__main__":  # pragma: no cover
    main()
