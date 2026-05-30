import { useEffect, useRef, useState } from "react";
import { startCall, sendChat } from "../lib/api.js";

const SUGGESTIONS = [
  "How much does it cost?",
  "It's too expensive",
  "How are you different from a local in-person tutor?",
  "Can I talk to a human?",
  "Not interested, no kids",
];

function decisionLine(d) {
  const bits = [`phase: ${d.phase}`];
  if (d.grounded_sources?.length) bits.push(`grounded: ${d.grounded_sources.join(", ")}`);
  if (d.objection) bits.push(`objection: ${d.objection}`);
  if (d.escalation) bits.push(`escalation: ${d.escalation}`);
  if (d.asked_field) bits.push(`asked: ${d.asked_field}`);
  return bits.join("  ·  ");
}

export default function Chat() {
  const [messages, setMessages] = useState([]);
  const [sessionId, setSessionId] = useState(null);
  const [input, setInput] = useState("");
  const [done, setDone] = useState(false);
  const logRef = useRef(null);

  async function start() {
    setMessages([]);
    setDone(false);
    const d = await startCall();
    setSessionId(d.session_id);
    setMessages([{ role: "agent", text: d.reply, trace: decisionLine(d) }]);
  }

  useEffect(() => { start(); }, []);
  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [messages]);

  async function submit(e) {
    e.preventDefault();
    const text = input.trim();
    if (!text || done || !sessionId) return;
    setInput("");
    setMessages((m) => [...m, { role: "you", text }]);
    const d = await sendChat(sessionId, text);
    if (d.error) {
      setMessages((m) => [...m, { role: "sys", text: d.error }]);
      return;
    }
    setMessages((m) => [...m, { role: "agent", text: d.reply, trace: decisionLine(d) }]);
    if (d.terminal) {
      setDone(true);
      setMessages((m) => [...m, { role: "sys", text: `Call ended (${d.outcome}).` }]);
    }
  }

  return (
    <div>
      <h1>Text chat</h1>
      <p className="sub">
        Talk to Vani by typing what a parent would say. Pricing is grounded from config,
        policy &amp; competitive answers are retrieval-only — every reply shows its decision trace.
      </p>
      <div className="statusbar">
        {SUGGESTIONS.map((s) => (
          <span key={s} className="pill" style={{ cursor: "pointer" }}
                onClick={() => !done && setInput(s)}>{s}</span>
        ))}
      </div>
      <div className="log" ref={logRef}>
        {messages.map((m, i) => (
          <div key={i} className={`msg ${m.role}`}>
            {m.text}
            {m.trace && <div className="trace">{m.trace}</div>}
          </div>
        ))}
      </div>
      <form className="composer" onSubmit={submit}>
        <input value={input} onChange={(e) => setInput(e.target.value)}
               placeholder="Type what the parent says…" disabled={done} autoFocus />
        <button className="btn primary" disabled={done}>Send</button>
        <button type="button" className="btn" onClick={start}>New call</button>
      </form>
    </div>
  );
}
