"""FastAPI chat UI for SalesFlow AI — talk to the agent "Alex" in the browser.

Drives the deterministic ``SalesAgent.respond()`` turn function over an
in-memory, per-session :class:`ConversationState`. **No API key is required**:
this serves the offline core — the exact engine the golden set and KPI gates
exercise — so pricing is grounded from config and policy answers are
retrieval-only. The optional LLM/voice layers are not needed to test the
conversation logic here.

Run locally:
    uvicorn salesflow.web:app --reload
    # or
    salesflow-web

Sessions live in process memory (the engine is deterministic and a demo needs
no durability); a restart clears them. On hosts that inject ``$PORT``
(Render/Fly/Railway) the launcher binds to it automatically.
"""

from __future__ import annotations

import os
import uuid

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from salesflow import AGENT_VERSION
from salesflow.agent.agent import AgentAction, SalesAgent
from salesflow.domain.models import ConversationState, Lead

app = FastAPI(title="SalesFlow AI — Alex", version=AGENT_VERSION)

_agent = SalesAgent()
_SESSIONS: dict[str, ConversationState] = {}


class ChatRequest(BaseModel):
    session_id: str
    message: str


def _new_phone() -> str:
    return "+1" + uuid.uuid4().hex[:10]


def _payload(state: ConversationState, action: AgentAction) -> dict[str, object]:
    """Serialise one agent turn + its decision trace for the client."""
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


# --- routes ----------------------------------------------------------------


@app.get("/healthz")
def healthz() -> JSONResponse:
    return JSONResponse({"status": "ok", "version": AGENT_VERSION})


@app.post("/api/start")
def start() -> JSONResponse:
    """Begin a new call: returns a session id + Alex's opening line."""
    session_id = uuid.uuid4().hex
    state = ConversationState(lead=Lead(phone=_new_phone()))
    _SESSIONS[session_id] = state
    action = _agent.open(state)
    payload = _payload(state, action)
    payload["session_id"] = session_id
    return JSONResponse(payload)


@app.post("/api/chat")
def chat(req: ChatRequest) -> JSONResponse:
    """One prospect turn -> one agent action (with full decision trace)."""
    state = _SESSIONS.get(req.session_id)
    if state is None:
        return JSONResponse(
            {"error": "unknown or expired session — start a new call"}, status_code=404
        )
    if state.phase.is_terminal:
        return JSONResponse(
            {"error": "this call has ended — start a new one", "terminal": True},
            status_code=409,
        )
    action = _agent.respond(state, req.message)
    return JSONResponse(_payload(state, action))


@app.get("/", response_class=HTMLResponse)
def home() -> HTMLResponse:
    return HTMLResponse(_PAGE)


def main() -> None:  # pragma: no cover - thin uvicorn launcher
    import uvicorn

    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run("salesflow.web:app", host="0.0.0.0", port=port)


# --- static single-page chat UI --------------------------------------------

_CSS = """
:root{--bg:#0f1419;--card:#1a212b;--line:#2a3441;--ink:#e6edf3;--mut:#8b98a5;
--good:#2ea043;--bad:#f85149;--warn:#d29922;--accent:#58a6ff}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font:15px/1.5 ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
.wrap{max-width:820px;margin:0 auto;padding:28px 20px 60px}
h1{font-size:24px;margin:0 0 4px}.sub{color:var(--mut);margin:0 0 18px;font-size:14px}
.banner{padding:12px 16px;border-radius:12px;border:1px solid var(--line);
background:var(--card);display:flex;gap:14px;align-items:center}
.pill{padding:3px 11px;border-radius:999px;font-size:12px;font-weight:600;
background:rgba(88,166,255,.16);color:var(--accent);white-space:nowrap}
.meta{color:var(--mut);font-size:13px;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.log{margin:16px 0;border:1px solid var(--line);background:var(--card);
border-radius:12px;padding:16px;height:54vh;overflow-y:auto;display:flex;
flex-direction:column;gap:10px}
.msg{max-width:80%;padding:10px 14px;border-radius:14px;white-space:pre-wrap;line-height:1.45}
.msg.agent{align-self:flex-start;background:#1f2a37;
border:1px solid var(--line);border-bottom-left-radius:4px}
.msg.you{align-self:flex-end;background:rgba(88,166,255,.16);
border:1px solid rgba(88,166,255,.35);border-bottom-right-radius:4px}
.msg.sys{align-self:center;color:var(--mut);font-size:13px;background:transparent;
border:1px dashed var(--line);max-width:90%;text-align:center}
.composer{display:flex;gap:10px}
.composer input{flex:1;padding:12px 14px;border-radius:10px;border:1px solid var(--line);
background:#0d1117;color:var(--ink);font-size:15px}
.composer input:focus{outline:none;border-color:var(--accent)}
.btn{padding:10px 16px;border-radius:10px;border:1px solid var(--line);
background:#22303f;color:var(--ink);font-weight:600;cursor:pointer}
.btn:hover{border-color:var(--accent)}.btn:disabled{opacity:.5;cursor:not-allowed}
.tips{margin:12px 0 0;color:var(--mut);font-size:13px}
.tips code{background:#0d1117;padding:1px 6px;border-radius:5px;color:var(--accent);cursor:pointer}
.foot{margin-top:22px;color:var(--mut);font-size:12px}
"""

_SCRIPT = """
const log=document.getElementById('log');
const form=document.getElementById('f');
const input=document.getElementById('m');
const phase=document.getElementById('phase');
const meta=document.getElementById('meta');
const sendBtn=document.getElementById('send');
let sessionId=null, terminal=false;

function bubble(role,text){
  const d=document.createElement('div');
  d.className='msg '+role; d.textContent=text;
  log.appendChild(d); log.scrollTop=log.scrollHeight;
}
function status(d){
  phase.textContent=d.phase;
  let s='outcome: '+d.outcome;
  if(d.grounded_sources&&d.grounded_sources.length){
    s+='  ·  grounded: '+d.grounded_sources.join(', ');}
  if(d.escalation){s+='  ·  escalation: '+d.escalation;}
  if(d.objection){s+='  ·  objection: '+d.objection;}
  meta.textContent=s;
}
async function start(){
  log.innerHTML=''; terminal=false; input.disabled=false; sendBtn.disabled=false;
  const r=await fetch('/api/start',{method:'POST'});
  const d=await r.json(); sessionId=d.session_id;
  bubble('agent',d.reply); status(d); input.focus();
}
async function send(text){
  bubble('you',text);
  const r=await fetch('/api/chat',{method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({session_id:sessionId,message:text})});
  const d=await r.json();
  if(d.error){bubble('sys',d.error);return;}
  bubble('agent',d.reply); status(d);
  if(d.terminal){terminal=true; input.disabled=true; sendBtn.disabled=true;
    bubble('sys','Call ended ('+d.outcome+'). Click “New call” to start over.');}
}
form.addEventListener('submit',e=>{e.preventDefault();
  const t=input.value.trim(); if(!t||terminal)return; input.value=''; send(t);});
document.getElementById('reset').addEventListener('click',start);
document.querySelectorAll('.tips code').forEach(el=>el.addEventListener('click',()=>{
  if(terminal)return; input.value=el.textContent; input.focus();}));
start();
"""

_PAGE = (
    "<!doctype html><html lang=en><head><meta charset=utf-8>"
    "<meta name=viewport content='width=device-width,initial-scale=1'>"
    "<title>SalesFlow AI — Alex</title><style>" + _CSS + "</style></head><body><div class=wrap>"
    "<h1>SalesFlow AI — talk to Alex</h1>"
    "<p class=sub>Autonomous tutoring sales agent. This is the deterministic offline core — "
    "no API key, the same engine the golden set + KPI gates exercise. "
    "Pricing is grounded from config; policy answers are retrieval-only.</p>"
    "<div class=banner><span class=pill id=phase>warmup</span>"
    "<span class=meta id=meta></span>"
    "<button id=reset class=btn>New call</button></div>"
    "<div id=log class=log></div>"
    "<form id=f class=composer>"
    "<input id=m autocomplete=off placeholder='Type what the parent says…'>"
    "<button id=send class=btn>Send</button></form>"
    "<p class=tips>Try: <code>How much does it cost?</code> "
    "<code>It's too expensive</code> <code>Can I talk to a human?</code> "
    "<code>What's your refund policy?</code> <code>Not interested, no kids</code></p>"
    "<p class=foot>JSON API · POST /api/start · POST /api/chat "
    "{session_id,message} · health /healthz</p>"
    "</div><script>" + _SCRIPT + "</script></body></html>"
)


if __name__ == "__main__":  # pragma: no cover
    main()
