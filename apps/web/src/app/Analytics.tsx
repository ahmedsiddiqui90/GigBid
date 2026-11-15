import { api } from "../lib/api/client";
import { useLoad } from "../lib/hooks";

type A = {
  by_category: Record<string, { analysed: number; submitted: number; replied: number; hired: number; reply_rate: number | null; hire_rate: number | null }>;
  connects_spent: number; cost_per_run_usd: number | null; p50_latency_s: number | null; p95_latency_s: number | null;
  top_rejection_reasons: [string, number][]; top_skip_reasons: [string, number][]; ab_test: Record<string, { submitted: number; replied: number }>;
};

const pct = (x: number | null) => (x == null ? "-" : `${Math.round(x * 100)}%`);

export default function Analytics() {
  const a = useLoad<A>(async () => (await api.GET("/api/analytics")).data as never, [], 15000);
  if (a.error) return <p className="error" role="alert">{a.error}</p>;
  if (!a.data) return <p role="status">Loading…</p>;
  const d = a.data;
  return (
    <div>
      <h1>Analytics</h1>
      <div className="grid2">
        <section className="card"><h2>Spend and speed</h2>
          <p>Connects spent: <b>{d.connects_spent}</b></p>
          <p>Cost per agent run: <b>{d.cost_per_run_usd != null ? `$${d.cost_per_run_usd}` : "-"}</b></p>
          <p>Latency p50 / p95: <b>{d.p50_latency_s?.toFixed(1) ?? "-"}s / {d.p95_latency_s?.toFixed(1) ?? "-"}s</b></p>
        </section>
        <section className="card"><h2>A/B proposal strategies</h2>
          <table><thead><tr><th>Arm</th><th>Submitted</th><th>Replied</th><th>Rate</th></tr></thead>
            <tbody>{Object.entries(d.ab_test).map(([k, v]) => <tr key={k}><td>{k}</td><td>{v.submitted}</td><td>{v.replied}</td><td>{pct(v.submitted ? v.replied / v.submitted : null)}</td></tr>)}</tbody></table>
        </section>
      </div>
      <section className="card"><h2>Reply and hire rate by category</h2>
        <table className="responsive"><thead><tr><th>Category</th><th>Analysed</th><th>Submitted</th><th>Reply rate</th><th>Hire rate</th></tr></thead>
          <tbody>{Object.entries(d.by_category).map(([k, v]) => <tr key={k}><td>{k}</td><td>{v.analysed}</td><td>{v.submitted}</td><td>{pct(v.reply_rate)}</td><td>{pct(v.hire_rate)}</td></tr>)}</tbody></table>
      </section>
      <div className="grid2">
        <section className="card"><h2>Top rejection reasons</h2>
          {d.top_rejection_reasons.length === 0 ? <p className="muted">None yet.</p> : <ul>{d.top_rejection_reasons.map(([r, n]) => <li key={r}>{r || "(no reason)"} - {n}</li>)}</ul>}
        </section>
        <section className="card"><h2>Top skip reasons</h2>
          <ul>{d.top_skip_reasons.map(([r, n]) => <li key={r}>{r} - {n}</li>)}</ul>
        </section>
      </div>
    </div>
  );
}
