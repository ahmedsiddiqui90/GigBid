import { useParams } from "react-router-dom";
import { RunTimeline } from "../components/RunTimeline";
import { api, unwrap } from "../lib/api/client";
import { useLoad } from "../lib/hooks";

type Run = { run: { run_id: string; status: string; trace_id: string; graph: string; usage: any[] }; steps: { node: string; ts: string; data: any }[]; trace_link: string | null };

export default function RunView() {
  const { id = "" } = useParams();
  const r = useLoad<Run>(() => unwrap(api.GET("/api/runs/{run_id}", { params: { path: { run_id: id } } })) as Promise<Run>, [id], 5000);
  if (r.error) return <p className="error" role="alert">{r.error}</p>;
  if (!r.data) return <p role="status">Loading…</p>;
  const u = r.data.run.usage ?? [];
  const tokens = u.reduce((s, x) => s + (x.tokens_in ?? 0) + (x.tokens_out ?? 0), 0);
  const cost = u.reduce((s, x) => s + (x.cost_usd ?? 0), 0);
  return (
    <div>
      <h1>Agent run {id}</h1>
      <p className="muted">Graph {r.data.run.graph} · trace id {r.data.run.trace_id} · {tokens} tokens · ${cost.toFixed(5)}
        {r.data.trace_link && <> · <a href={r.data.trace_link} target="_blank" rel="noreferrer">full trace</a></>}</p>
      <section className="card"><h2>Live progress</h2><RunTimeline runId={id} /></section>
      <section className="card">
        <h2>Execution trace</h2>
        {r.data.steps.map((s, i) => (
          <details key={i}><summary>{s.node} <span className="muted">{new Date(s.ts).toLocaleTimeString()}</span></summary><pre>{JSON.stringify(s.data, null, 1)}</pre></details>
        ))}
      </section>
      <section className="card">
        <h2>Tokens and cost per node</h2>
        <table><thead><tr><th>Node</th><th>Model</th><th>Tokens</th><th>USD</th><th>s</th></tr></thead>
          <tbody>{u.map((x, i) => <tr key={i}><td>{x.node}</td><td>{x.model}</td><td>{(x.tokens_in ?? 0) + (x.tokens_out ?? 0)}</td><td>{(x.cost_usd ?? 0).toFixed(5)}</td><td>{(x.latency_s ?? 0).toFixed(2)}</td></tr>)}</tbody>
        </table>
      </section>
    </div>
  );
}
