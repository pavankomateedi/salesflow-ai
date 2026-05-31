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
  const [callStarted, setCallStarted] = useState(false);
  const [ended, setEnded] = useState(false);
  const [input, setInput] = useState("");
  const [micLevel, setMicLevel] = useState(0); // 0..1 for the live meter (rAF-throttled)

  const wsRef = useRef(null);
  const ctxRef = useRef(null);
  // Refs that mirror state for the ScriptProcessor onaudioprocess closure —
  // React state via closure is stale because the audio callback is bound once
  // at startMic and never re-rendered. agentSpeakingRef fixes barge-in.
  const agentSpeakingRef = useRef(false);
  const micLevelRef = useRef(0);
  const levelRafRef = useRef(null);
  const srcRef = useRef(null); // current playing source (for barge-in)
  const micRef = useRef(null); // { stream, processor }
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
    (agentSpeakingRef.current = false, setAgentSpeaking(false));
  }

  function playPcm(b64, sampleRate) {
    const c = ctx();
    if (c.state === "suspended") c.resume().catch(() => {});
    const buffer = pcm16ToAudioBuffer(c, b64, sampleRate);
    const source = c.createBufferSource();
    source.buffer = buffer;
    source.connect(c.destination);
    source.onended = () => {
      if (srcRef.current === source) { srcRef.current = null; (agentSpeakingRef.current = false, setAgentSpeaking(false)); }
    };
    srcRef.current = source;
    agentSpeakingRef.current = true;
    setAgentSpeaking(true);
    source.start();
  }

  function connect() {
    setMessages([]); setEnded(false);
    const ws = new WebSocket(wsUrl("/ws/voice"));
    wsRef.current = ws;
    ws.onopen = () => setConnected(true);
    ws.onclose = () => { setConnected(false); setListening(false); };
    ws.onmessage = (ev) => {
      let d;
      try {
        d = JSON.parse(ev.data);
      } catch (e) {
        append("sys", `dropped malformed server frame: ${e.message}`);
        return;
      }
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

  // Status only fetched on mount; WebSocket + mic start when the user clicks Begin.
  useEffect(() => {
    voiceStatus().then(setStatus);
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

  // --- live mic capture (always on once the call has started) ---
  async function startMic() {
    if (micRef.current) return; // already running
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const c = ctx();
    if (c.state === "suspended") await c.resume().catch(() => {});
    const sourceNode = c.createMediaStreamSource(stream);
    const processor = c.createScriptProcessor(4096, 1, 1);
    let buffered = [];
    let speaking = false;
    let lastVoice = 0;

    // Pump the smoothed level into a ref every audio block, then flush to React
    // state once per animation frame so the meter looks continuous but Voice.jsx
    // doesn't re-render 11×/sec. The whole tree (transcript + status pills) was
    // re-rendering on every audio block before this.
    if (levelRafRef.current == null) {
      const flush = () => {
        setMicLevel(micLevelRef.current);
        levelRafRef.current = requestAnimationFrame(flush);
      };
      levelRafRef.current = requestAnimationFrame(flush);
    }

    processor.onaudioprocess = (e) => {
      const frame = e.inputBuffer.getChannelData(0);
      const level = rms(frame);
      // Smooth the displayed level so the meter doesn't jitter wildly.
      micLevelRef.current = micLevelRef.current * 0.6 + Math.min(1, level * 8) * 0.4;
      const now = performance.now();
      if (level > SPEAK_THRESHOLD) {
        // Read agentSpeaking via REF, not closure — the ScriptProcessor callback
        // is bound once and would otherwise see the stale initial `false` value,
        // breaking barge-in for the whole call.
        if (agentSpeakingRef.current) {
          wsRef.current?.send(JSON.stringify({ type: "barge" }));
          stopPlayback();
        }
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
    if (levelRafRef.current != null) {
      cancelAnimationFrame(levelRafRef.current);
      levelRafRef.current = null;
    }
    micLevelRef.current = 0;
    setListening(false);
    setMicLevel(0);
  }

  async function beginCall() {
    // One user gesture grants mic permission, unsuspends the AudioContext,
    // opens the WebSocket, and starts continuous capture. After this, the
    // mic stays on for the whole call — no further Start/Stop required.
    setCallStarted(true);
    try { await startMic(); } catch (e) { append("sys", `mic blocked: ${e.message}`); return; }
    connect();
  }

  function endCall() {
    stopMic();
    wsRef.current?.close();
    setCallStarted(false);
    setEnded(false);
    setMessages([]);
  }

  function restartCall() {
    stopMic();
    wsRef.current?.close();
    setMessages([]); setEnded(false);
    // Reuse the existing user gesture (this is fired from a button click).
    startMic().then(connect).catch((e) => append("sys", `mic blocked: ${e.message}`));
  }

  const available = status?.available;

  return (
    <div>
      <h1>Live voice</h1>
      <p className="sub">
        One click to begin — then Vani listens continuously, detects each utterance
        by silence, and replies in real time. Cartesia powers STT+TTS; OpenAI rephrases.
      </p>

      <div className="statusbar">
        <span className={`pill ${connected ? "good" : "warn"}`}>
          {connected ? "connected" : (callStarted ? "connecting…" : "ready")}
        </span>
        <span className={`pill ${available ? "good" : "warn"}`}>
          {available ? "Cartesia voice live" : "no voice key — text fallback"}
        </span>
        {agentSpeaking && <span className="pill">Vani speaking…</span>}
        {listening && !agentSpeaking && <span className="pill good">listening…</span>}
        {status && <span className="muted">{status.note}</span>}
      </div>

      {/* live mic-level meter (only visible while the call is active) */}
      {callStarted && available && (
        <div style={{
          height: 4, background: "rgba(148,163,184,.18)",
          borderRadius: 999, overflow: "hidden", margin: "0 0 14px",
        }}>
          <div style={{
            height: "100%",
            width: `${Math.min(100, micLevel * 100)}%`,
            background: agentSpeaking
              ? "linear-gradient(90deg, var(--purple), var(--pink))"
              : "linear-gradient(90deg, var(--teal), var(--purple))",
            transition: "width 80ms ease-out",
          }} />
        </div>
      )}

      <div className="log" ref={logRef}>
        {messages.length === 0 && (
          <div className="center">
            {available
              ? (callStarted ? "Connecting… Vani will greet you." : "Click Begin call — Vani will greet you and start listening.")
              : "Type the prospect's line below to drive the loop."}
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`msg ${m.role}`}>
            {m.text}
            {m.trace && <div className="trace">{m.trace}</div>}
          </div>
        ))}
      </div>

      {available ? (
        <div className="composer">
          {!callStarted ? (
            <button className="btn primary" onClick={beginCall} disabled={ended}>
              🎙 Begin call
            </button>
          ) : (
            <>
              <button className="btn danger" onClick={endCall}>■ End call</button>
              <button type="button" className="btn" onClick={restartCall}>↻ New call</button>
            </>
          )}
        </div>
      ) : (
        <form className="composer" onSubmit={(e) => {
          e.preventDefault();
          if (!connected) connect();
          sendText(input);
          setInput("");
        }}>
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="No voice key — type the prospect's line to drive the loop…"
            disabled={ended}
          />
          <button className="btn primary" disabled={ended}>Send</button>
          <button type="button" className="btn" onClick={() => { setMessages([]); setEnded(false); connect(); }}>
            New call
          </button>
        </form>
      )}
    </div>
  );
}
