import { useEffect, useState } from "react";
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
  return typeof v === "number" && v <= 1 ? `${(v * 100).toFixed(0)}%` : Number(v).toFixed(2);
}

export default function Dashboard() {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    fetchKpis(200).then(setData).catch((e) => setErr(String(e)));
  }, []);

  if (err) return <div className="center">Failed to load KPIs: {err}</div>;
  if (!data) return <div className="center">Running self-play + A/B experiment…</div>;

  const kpis = data.kpis || {};
  const ab = data.ab || {};
  const t = data.sample_transcript || {};

  return (
    <div>
      <h1>Observability dashboard</h1>
      <p className="sub">
        Live self-play KPIs, the recursive A/B improvement loop, and a PII-redacted
        transcript with per-turn decisions — version <code>{data.agent_version}</code>.
      </p>

      <div className="cards">
        {Object.entries(KPI_LABELS).map(([k, label]) =>
          k in kpis ? (
            <div className="kpi" key={k}>
              <div className="v">{KPI_LABELS[k].includes("turns") ? Number(kpis[k]).toFixed(1) : pct(kpis[k])}</div>
              <div className="k">{label}</div>
            </div>
          ) : null
        )}
        <div className="kpi">
          <div className="v" style={{ color: data.hallucination_rate === 0 ? "var(--good)" : "var(--bad)" }}>
            {pct(data.hallucination_rate)}
          </div>
          <div className="k">Hallucination</div>
        </div>
      </div>

      <h2>Self-play outcomes (adversarial personas)</h2>
      <table>
        <thead><tr><th>Call</th><th>Outcome</th><th>Final phase</th><th>Escalation</th><th className="num">Turns</th></tr></thead>
        <tbody>
          {(data.calls || []).map((c) => (
            <tr key={c.session_id}>
              <td>{c.session_id}</td>
              <td>{c.outcome}</td>
              <td>{c.final_phase}</td>
              <td>{c.escalation_trigger || "—"}</td>
              <td className="num">{c.turns}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <h2>Recursive improvement — A/B price framing (baseline <code>{ab.baseline}</code>, n={ab.n_per_variant}/variant)</h2>
      <table>
        <thead><tr><th>Variant</th><th className="num">Conv. rate</th><th className="num">Lift</th><th className="num">p-value</th><th>Decision</th></tr></thead>
        <tbody>
          {(ab.variants || []).map((v) => {
            const isBest = v.name === ab.best;
            const cls = v.lift > 0 ? "up" : v.lift < 0 ? "down" : "flat";
            const decision = v.name === ab.baseline ? "baseline"
              : v.significant ? (isBest ? "promote ✓" : "significant") : "retire (n.s.)";
            return (
              <tr key={v.name}>
                <td>{v.name}{isBest ? " ★" : ""}</td>
                <td className="num">{pct(v.rate)}</td>
                <td className={`num ${cls}`}>{v.lift >= 0 ? "+" : ""}{(v.lift * 100).toFixed(1)}pp</td>
                <td className="num">{v.p_value < 0.001 ? v.p_value.toExponential(1) : v.p_value.toFixed(3)}</td>
                <td>{decision}</td>
              </tr>
            );
          })}
        </tbody>
      </table>

      <h2>Sample transcript {t.redacted && <span className="pill good">PII-redacted</span>}</h2>
      <div className="log" style={{ height: "auto", maxHeight: "44vh" }}>
        {(t.turns || []).map((turn, i) => (
          <div key={i} className={`msg ${turn.speaker === "agent" ? "agent" : "you"}`}>
            {turn.text}
            {turn.decision && Object.keys(turn.decision).length > 0 && (
              <div className="trace">{Object.entries(turn.decision).map(([k, v]) => `${k}=${JSON.stringify(v)}`).join("  ·  ")}</div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
