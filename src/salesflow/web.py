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

import asyncio
import base64
import os
import uuid
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from salesflow import AGENT_VERSION
from salesflow.agent.agent import AgentAction, SalesAgent
from salesflow.domain.models import CallLog, ConversationState, Lead
from salesflow.eval.dashboard import build_dashboard
from salesflow.llm import get_client
from salesflow.voice.factory import get_stt, get_tts, voice_available
from salesflow.voice.interfaces import AudioChunk

app = FastAPI(title="SalesFlow AI — Vani", version=AGENT_VERSION)

# Live agent uses OpenAI when OPENAI_API_KEY is set (natural phrasing); mock
# otherwise. Tests still construct ``SalesAgent()`` directly => mock => no LLM
# calls in the suite, so determinism is preserved.
_agent = SalesAgent(llm=get_client())
_SESSIONS: dict[str, ConversationState] = {}
# Real calls that ran on this server, captured at terminal state and shown on
# the dashboard alongside the synthetic baseline.
_LIVE_CALLS: list[CallLog] = []
_RECORDED: set[str] = set()


def _record_call(session_id: str, state: ConversationState) -> None:
    """Snapshot the call into the live-stats store. Idempotent via ``_RECORDED``.

    Called from BOTH the natural terminal-phase path (CLOSE / ESCALATION /
    GRACEFUL_EXIT) and the websocket-close path (abandoned mid-call). The
    abandoned case keeps ``state.outcome == IN_PROGRESS`` and the final phase
    wherever the parent stopped, so the dashboard reflects every conversation
    the user actually had — not just the ones that ran to completion.
    """
    if session_id in _RECORDED:
        return
    if not state.turns:  # nothing happened — nothing worth recording
        return
    _LIVE_CALLS.append(
        CallLog(
            session_id=session_id,
            phone=state.lead.phone,
            agent_version=AGENT_VERSION,
            turns=list(state.turns),
            outcome=state.outcome,
            final_phase=state.phase,
            escalation_trigger=state.escalation_trigger,
            collected_fields=dict(state.lead.all_fields),
            decisions=[t.decision for t in state.turns if t.speaker == "agent" and t.decision],
        )
    )
    _RECORDED.add(session_id)

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
    action = _agent.respond(state, req.message)
    if state.phase.is_terminal:
        _record_call(req.session_id, state)
    return JSONResponse(_payload(state, action))


@app.get("/api/kpis")
def api_kpis(n_ab: int = 200) -> JSONResponse:
    """Dynamic dashboard data: live calls + synthetic baseline. Not cached so
    each request reflects the most recent terminated calls on this server."""
    return JSONResponse(
        build_dashboard(n_ab=max(20, min(2000, n_ab)), live_calls=list(_LIVE_CALLS))
    )


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


@app.get("/api/status")
def status() -> JSONResponse:
    """All-backend status: confirms the LLM phrasing layer + Cartesia voice are
    actually wired into the running process. If ``llm.backend == "mock"`` the
    natural phrasing / smart extraction / LLM recap are off — most likely
    because ``OPENAI_API_KEY`` wasn't exported into the shell before uvicorn started.
    """
    return JSONResponse(
        {
            "agent_version": AGENT_VERSION,
            "agent_persona": "Vani",
            "llm": {
                "backend": _agent.llm.name,
                "natural_phrasing": _agent.llm.name != "mock",
                "smart_extraction": _agent.llm.name != "mock",
                "llm_recap_review": _agent.llm.name != "mock",
            },
            "voice": {
                "available": voice_available(),
                "stt": "cartesia" if voice_available() else "mock",
                "tts": "cartesia" if voice_available() else "mock",
            },
            "live_calls_recorded": len(_LIVE_CALLS),
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
    session_id = uuid.uuid4().hex
    state = ConversationState(lead=Lead(phone=_new_phone()))
    opening = await asyncio.to_thread(_agent.open, state)
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
                rate = int(msg.get("sample_rate") or 16000)
                try:
                    transcript = await asyncio.to_thread(
                        get_stt().transcribe,
                        AudioChunk(duration_ms=0, pcm=pcm, sample_rate=rate),
                    )
                    text = transcript.text
                except Exception as exc:
                    # Don't crash the websocket on a single STT failure — the user
                    # would just see "disconnected" and lose the call. Surface the
                    # error and keep the loop alive so they can retry.
                    await ws.send_json({"type": "audio_error", "detail": f"STT: {exc}"})
                    continue
            if not text.strip():
                continue
            if state.phase.is_terminal:
                await ws.send_json({"type": "ended", "outcome": state.outcome.value})
                break

            # Sync agent call (incl. optional LLM phrasing) goes off the event loop
            # so concurrent websocket connections don't block one another.
            action = await asyncio.to_thread(_agent.respond, state, text)
            await ws.send_json({"type": "reply", "transcript": text, **_payload(state, action)})
            await _send_audio(ws, action.utterance)
            if state.phase.is_terminal:
                _record_call(session_id, state)
                await ws.send_json({"type": "ended", "outcome": state.outcome.value})
                break
    except WebSocketDisconnect:
        pass
    finally:
        # Even if the user clicked "End call" / "New call" before reaching a
        # terminal phase, the conversation still happened — capture it so the
        # dashboard reflects every call, not just the ones that ran to close.
        _record_call(session_id, state)


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
    "<title>SalesFlow AI — Vani</title>"
    "<style>body{margin:0;color:#f1f5f9;font:15px/1.5 system-ui,sans-serif;min-height:100vh;"
    "background:radial-gradient(ellipse 1000px 700px at -5% 5%,"
    "rgba(34,211,238,.40),transparent 55%),"
    "radial-gradient(ellipse 900px 700px at 105% 95%,rgba(236,72,153,.45),transparent 55%),"
    "radial-gradient(ellipse 700px 500px at 55% 55%,rgba(139,92,246,.35),transparent 60%),#0c0f24;"
    "background-attachment:fixed}.wrap{max-width:720px;margin:0 auto;padding:32px 20px}"
    "h1{font-size:24px;background:linear-gradient(90deg,#22d3ee,#8b5cf6 55%,#ec4899);"
    "-webkit-background-clip:text;background-clip:text;color:transparent}"
    "a{color:#22d3ee}code{background:rgba(34,211,238,.12);padding:2px 7px;border-radius:6px;"
    "color:#22d3ee;border:1px solid rgba(34,211,238,.25)}"
    ".log{border:1px solid rgba(148,163,184,.18);background:rgba(20,24,50,.55);"
    "backdrop-filter:blur(18px) saturate(140%);border-radius:14px;padding:16px;height:52vh;"
    "overflow-y:auto;display:flex;flex-direction:column;gap:10px;margin:16px 0}"
    ".msg{max-width:80%;padding:11px 15px;border-radius:16px;white-space:pre-wrap;"
    "border:1px solid rgba(148,163,184,.18)}"
    ".agent{align-self:flex-start;background:linear-gradient(135deg,rgba(139,92,246,.22),"
    "rgba(34,211,238,.10));border-color:rgba(139,92,246,.30);border-bottom-left-radius:4px}"
    ".you{align-self:flex-end;background:linear-gradient(135deg,rgba(34,211,238,.22),"
    "rgba(236,72,153,.18));border-color:rgba(34,211,238,.40);border-bottom-right-radius:4px}"
    "form{display:flex;gap:10px}"
    "input{flex:1;padding:12px 16px;border-radius:12px;border:1px solid rgba(148,163,184,.18);"
    "background:rgba(7,10,28,.55);color:#f1f5f9}"
    "input:focus{outline:none;border-color:#22d3ee;box-shadow:0 0 0 3px rgba(34,211,238,.22)}"
    "button{padding:10px 18px;border-radius:12px;border:0;color:#06121f;font-weight:700;"
    "cursor:pointer;background:linear-gradient(135deg,#22d3ee,#8b5cf6 65%,#ec4899);"
    "box-shadow:0 10px 24px rgba(34,211,238,.25)}</style></head>"
    "<body><div class=wrap><h1>SalesFlow AI — talk to Vani</h1>"
    "<p>React UI not built — serving the lightweight fallback chat. "
    "Build the SPA for the voice + dashboard experience: "
    "<code>cd frontend &amp;&amp; npm install &amp;&amp; npm run build</code>.</p>"
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
