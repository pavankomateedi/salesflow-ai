import { useEffect, useRef, useState } from "react";
import { voiceStatus, wsUrl } from "../lib/api.js";
import { pcm16ToAudioBuffer, float32ToPcm16Base64, rms } from "../lib/audio.js";

const SPEAK_THRESHOLD = 0.02; // RMS gate for "is the prospect speaking"
const SILENCE_MS = 700; // trailing silence that ends an utterance

function decisionLine(d) {
  const bits = [`phase: ${d.phase}`];
  if (d.grounded_sources?.length) bits.push(`grounded: ${d.grounded_sources.join(", ")}`);
  if (d.objection) bits.push(`objection: ${d.objection}`);
  if (d.escalation) bits.push(`escalation: ${d.escalation}`);
  return bits.join("  ·  ");
}

export default function Voice() {
  const [status, setStatus] = useState(null);
  const [messages, setMessages] = useState([]);
  const [connected, setConnected] = useState(false);
  const [agentSpeaking, setAgentSpeaking] = useState(false);
  const [listening, setListening] = useState(false);
  const [ended, setEnded] = useState(false);
  const [input, setInput] = useState("");

  const wsRef = useRef(null);
  const ctxRef = useRef(null);
  const srcRef = useRef(null); // current playing source (for barge-in)
  const micRef = useRef(null); // { stream, ctx, processor }
  const logRef = useRef(null);

  function append(role, text, trace) {
    setMessages((m) => [...m, { role, text, trace }]);
  }

  function ctx() {
    if (!ctxRef.current) ctxRef.current = new (window.AudioContext || window.webkitAudioContext)();
    return ctxRef.current;
  }

  function stopPlayback() {
    if (srcRef.current) {
      try { srcRef.current.stop(); } catch { /* already stopped */ }
      srcRef.current = null;
    }
    setAgentSpeaking(false);
  }

  function playPcm(b64, sampleRate) {
    const c = ctx();
    const buffer = pcm16ToAudioBuffer(c, b64, sampleRate);
    const source = c.createBufferSource();
    source.buffer = buffer;
    source.connect(c.destination);
    source.onended = () => { if (srcRef.current === source) { srcRef.current = null; setAgentSpeaking(false); } };
    srcRef.current = source;
    setAgentSpeaking(true);
    source.start();
  }

  function connect() {
    setMessages([]); setEnded(false);
    const ws = new WebSocket(wsUrl("/ws/voice"));
    wsRef.current = ws;
    ws.onopen = () => setConnected(true);
    ws.onclose = () => setConnected(false);
    ws.onmessage = (ev) => {
      const d = JSON.parse(ev.data);
      if (d.type === "reply") {
        if (d.transcript) append("you", d.transcript);
        append("agent", d.reply, decisionLine(d));
      } else if (d.type === "audio") {
        playPcm(d.b64, d.sample_rate);
      } else if (d.type === "ended") {
        setEnded(true);
        append("sys", `Call ended (${d.outcome}).`);
      } else if (d.type === "audio_error") {
        append("sys", `voice backend: ${d.detail}`);
      }
    };
  }

  useEffect(() => {
    voiceStatus().then(setStatus);
    connect();
    return () => {
      wsRef.current?.close();
      stopMic();
      ctxRef.current?.close?.();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [messages]);

  function sendText(text) {
    const t = text.trim();
    if (!t || ended || wsRef.current?.readyState !== WebSocket.OPEN) return;
    if (agentSpeaking) { wsRef.current.send(JSON.stringify({ type: "barge" })); stopPlayback(); }
    wsRef.current.send(JSON.stringify({ type: "utterance", text: t }));
  }

  // --- live mic capture (used when Cartesia voice is available) ---
  async function startMic() {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const c = ctx();
    const sourceNode = c.createMediaStreamSource(stream);
    const processor = c.createScriptProcessor(4096, 1, 1);
    let buffered = [];
    let speaking = false;
    let lastVoice = 0;

    processor.onaudioprocess = (e) => {
      const frame = e.inputBuffer.getChannelData(0);
      const level = rms(frame);
      const now = performance.now();
      if (level > SPEAK_THRESHOLD) {
        if (agentSpeaking) { wsRef.current?.send(JSON.stringify({ type: "barge" })); stopPlayback(); }
        speaking = true;
        lastVoice = now;
        buffered.push(new Float32Array(frame));
      } else if (speaking && now - lastVoice > SILENCE_MS) {
        // utterance complete -> flush to server as one PCM16 chunk
        const total = buffered.reduce((n, f) => n + f.length, 0);
        const merged = new Float32Array(total);
        let off = 0;
        for (const f of buffered) { merged.set(f, off); off += f.length; }
        buffered = []; speaking = false;
        if (total > 0 && wsRef.current?.readyState === WebSocket.OPEN) {
          wsRef.current.send(JSON.stringify({
            type: "utterance",
            audio_b64: float32ToPcm16Base64(merged),
            sample_rate: c.sampleRate,
          }));
        }
      } else if (speaking) {
        buffered.push(new Float32Array(frame));
      }
    };
    sourceNode.connect(processor);
    processor.connect(c.destination);
    micRef.current = { stream, processor, sourceNode };
    setListening(true);
  }

  function stopMic() {
    const m = micRef.current;
    if (!m) return;
    try { m.processor.disconnect(); m.sourceNode.disconnect(); } catch { /* noop */ }
    m.stream.getTracks().forEach((t) => t.stop());
    micRef.current = null;
    setListening(false);
  }

  const available = status?.available;

  return (
    <div>
      <h1>Live voice</h1>
      <p className="sub">
        Real-time voice loop over WebSocket: prospect speech → STT → the deterministic agent → TTS,
        with barge-in. Cartesia powers STT+TTS when a key is set.
      </p>
      <div className="statusbar">
        <span className={`pill ${connected ? "good" : "bad"}`}>{connected ? "connected" : "disconnected"}</span>
        <span className={`pill ${available ? "good" : "warn"}`}>
          {available ? "Cartesia voice live" : "no voice key — text fallback"}
        </span>
        {agentSpeaking && <span className="pill">Vani speaking…</span>}
        {listening && <span className="pill good">listening…</span>}
        {status && <span className="muted">{status.note}</span>}
      </div>

      <div className="log" ref={logRef}>
        {messages.length === 0 && <div className="center">Connecting… Vani will greet you.</div>}
        {messages.map((m, i) => (
          <div key={i} className={`msg ${m.role}`}>
            {m.text}
            {m.trace && <div className="trace">{m.trace}</div>}
          </div>
        ))}
      </div>

      {available ? (
        <div className="composer">
          {!listening ? (
            <button className="btn primary" onClick={startMic} disabled={ended}>🎙 Start talking</button>
          ) : (
            <button className="btn danger" onClick={stopMic}>■ Stop mic</button>
          )}
          <button type="button" className="btn" onClick={() => { stopMic(); connect(); }}>New call</button>
        </div>
      ) : (
        <form className="composer" onSubmit={(e) => { e.preventDefault(); sendText(input); setInput(""); }}>
          <input value={input} onChange={(e) => setInput(e.target.value)}
                 placeholder="No voice key — type the prospect's line to drive the loop…" disabled={ended} />
          <button className="btn primary" disabled={ended}>Send</button>
          <button type="button" className="btn" onClick={connect}>New call</button>
        </form>
      )}
    </div>
  );
}
