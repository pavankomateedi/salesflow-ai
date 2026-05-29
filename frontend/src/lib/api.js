export async function startCall() {
  const r = await fetch("/api/start", { method: "POST" });
  return r.json();
}

export async function sendChat(sessionId, message) {
  const r = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, message }),
  });
  return r.json();
}

export async function fetchKpis(nAb = 200) {
  const r = await fetch(`/api/kpis?n_ab=${nAb}`);
  if (!r.ok) throw new Error(`kpis ${r.status}`);
  return r.json();
}

export async function voiceStatus() {
  const r = await fetch("/api/voice/status");
  return r.json();
}

export function wsUrl(path) {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${location.host}${path}`;
}
