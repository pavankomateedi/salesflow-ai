import { useEffect, useRef, useState } from "react";
import { fetchKpis } from "../lib/api.js";

const KPI_LABELS = {
  conversion_rate: "Conversion",
  discovery_completion_rate: "Discovery done",
  escalation_rate: "Escalation",
  objection_to_close_rate: "Objection→close",
  false_positive_close_rate: "False closes",
  avg_handle_turns: "Avg turns",
  transcript_quality: "Transcript qual.",
};

function pct(v) {
  if (v === null || v === undefined) return "—";
  return typeof v === "number" && v <= 1 ? `${(v * 100).toFixed(0)}%` : Number(v).toFixed(2);
}

function KpiCards({ kpis, hallucination }) {
  if (!kpis) {
    return (
      <div className="muted" style={{ marginBottom: 16 }}>
        No KPIs yet — finish a call on Chat or Voice and refresh.
      </div>
    );
  }
  return (
    <div className="cards">
      {Object.entries(KPI_LABELS).map(([k, label]) =>
        k in kpis ? (
          <div className="kpi" key={k}>
            <div className="v">
              {label.includes("turns") ? Number(kpis[k]).toFixed(1) : pct(kpis[k])}
            </div>
            <div className="k">{label}</div>
          </div>
        ) : null
      )}
      {hallucination !== undefined && (
        <div className="kpi">
          <div className="v" style={{ color: hallucination === 0 ? "var(--good)" : "var(--bad)" }}>
            {pct(hallucination)}
          </div>
          <div className="k">Hallucination</div>
        </div>
      )}
    </div>
  );
}

function CallsTable({ calls }) {
  if (!calls?.length) return <p className="muted">No calls yet.</p>;
  return (
    <table>
      <thead>
        <tr>
          <th>Call</th>
          <th>Outcome</th>
          <th>Final phase</th>
          <th>Escalation</th>
          <th className="num">Turns</th>
          <th>Collected</th>
        </tr>
      </thead>
      <tbody>
        {calls.map((c) => (
          <tr key={c.session_id}>
            <td><code>{c.session_id.slice(0, 8)}</code></td>
            <td>{c.outcome}</td>
            <td>{c.final_phase}</td>
            <td>{c.escalation_trigger || "—"}</td>
            <td className="num">{c.turns}</td>
            <td className="muted">{(c.collected_fields || []).join(", ") || "—"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Transcript({ t }) {
  if (!t?.turns?.length) return null;
  return (
    <>
      <h2>Sample transcript {t.redacted && <span className="pill good">PII-redacted</span>}</h2>
      <div className="log" style={{ height: "auto", maxHeight: "44vh" }}>
        {t.turns.map((turn, i) => (
          <div key={i} className={`msg ${turn.speaker === "agent" ? "agent" : "you"}`}>
            {turn.text}
            {turn.decision && Object.keys(turn.decision).length > 0 && (
              <div className="trace">
                {Object.entries(turn.decision)
                  .map(([k, v]) => `${k}=${JSON.stringify(v)}`)
                  .join("  ·  ")}
              </div>
            )}
          </div>
        ))}
      </div>
    </>
  );
}

export default function Dashboard() {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  const [loading, setLoading] = useState(true);
  const [lastUpdated, setLastUpdated] = useState(null);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const timerRef = useRef(null);

  function load() {
    setLoading(true);
    fetchKpis(200)
      .then((d) => { setData(d); setLastUpdated(new Date()); setErr(null); })
      .catch((e) => setErr(String(e)))
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    load();
  }, []);

  useEffect(() => {
    if (timerRef.current) clearInterval(timerRef.current);
    if (autoRefresh) timerRef.current = setInterval(load, 8000);
    return () => { if (timerRef.current) clearInterval(timerRef.current); };
  }, [autoRefresh]);

  if (err && !data) return <div className="center">Failed to load KPIs: {err}</div>;
  if (!data) return <div className="center">Running self-play + A/B experiment…</div>;

  const live = data.live || { n_calls: 0, kpis: null, calls: [], sample_transcript: null };
  const synthetic = data.synthetic || { n_calls: 0, kpis: data.kpis, calls: data.calls };
  const ab = data.ab || {};

  return (
    <div>
      <h1>Observability dashboard</h1>
      <p className="sub">
        Live KPIs from <em>your</em> calls on this server, plus the synthetic baseline
        and the recursive A/B improvement loop — version <code>{data.agent_version}</code>.
      </p>

      <div className="statusbar">
        <button className="btn primary" onClick={load} disabled={loading}>
          {loading ? "Refreshing…" : "↻ Refresh"}
        </button>
        <label className="muted" style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <input
            type="checkbox"
            checked={autoRefresh}
            onChange={(e) => setAutoRefresh(e.target.checked)}
          />
          auto-refresh (8s)
        </label>
        {lastUpdated && (
          <span className="muted">last update {lastUpdated.toLocaleTimeString()}</span>
        )}
        <span className={`pill ${live.n_calls > 0 ? "good" : "warn"}`}>
          {live.n_calls} live call{live.n_calls === 1 ? "" : "s"}
        </span>
      </div>

      <h2>Your live calls {live.n_calls > 0 && <span className="pill good">live</span>}</h2>
      <KpiCards kpis={live.kpis} hallucination={live.n_calls > 0 ? data.hallucination_rate : undefined} />
      <CallsTable calls={live.calls} />
      <Transcript t={live.sample_transcript} />

      <h2>Synthetic baseline — 5 adversarial personas</h2>
      <KpiCards kpis={synthetic.kpis} />
      <CallsTable calls={synthetic.calls} />

      <h2>
        Recursive improvement — A/B price framing
        {ab.baseline && (
          <>
            {" "}(baseline <code>{ab.baseline}</code>, n={ab.n_per_variant}/variant)
          </>
        )}
      </h2>
      <table>
        <thead>
          <tr>
            <th>Variant</th>
            <th className="num">Conv. rate</th>
            <th className="num">Lift</th>
            <th className="num">p-value</th>
            <th>Decision</th>
          </tr>
        </thead>
        <tbody>
          {(ab.variants || []).map((v) => {
            const isBest = v.name === ab.best;
            const cls = v.lift > 0 ? "up" : v.lift < 0 ? "down" : "flat";
            const decision = v.name === ab.baseline
              ? "baseline"
              : v.significant
                ? (isBest ? "promote ✓" : "significant")
                : "retire (n.s.)";
            return (
              <tr key={v.name}>
                <td>{v.name}{isBest ? " ★" : ""}</td>
                <td className="num">{pct(v.rate)}</td>
                <td className={`num ${cls}`}>
                  {v.lift >= 0 ? "+" : ""}{(v.lift * 100).toFixed(1)}pp
                </td>
                <td className="num">
                  {v.p_value < 0.001 ? v.p_value.toExponential(1) : v.p_value.toFixed(3)}
                </td>
                <td>{decision}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
