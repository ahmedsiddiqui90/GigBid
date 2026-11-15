import { Link, useParams } from "react-router-dom";
import { api, unwrap } from "../lib/api/client";
import { useLoad } from "../lib/hooks";
import { RiskBadges } from "./Inbox";

type Detail = {
  row: { title: string; status: string; fit?: number; risk?: number; risk_flags?: string[]; price?: number; decision?: string };
  job: { description?: string; budget?: { type?: string; min?: number; max?: number }; skills?: string[]; connects_cost?: number };
  analysis: Record<string, any>;
  approval: { id: number; status: string } | null;
  runs: { run_id: string; status: string; trace_id: string; started_at: string }[];
};

export default function JobDetail() {
  const { id = "" } = useParams();
  const d = useLoad<Detail>(() => unwrap(api.GET("/api/jobs/{job_id}", { params: { path: { job_id: id } } })) as Promise<Detail>, [id], 6000);
  if (d.error) return <p className="error" role="alert">{d.error}</p>;
  if (!d.data) return <p role="status">Loading…</p>;
  const { row, job, analysis: a } = d.data;
  const spec = a.job_spec ?? {};
  return (
    <div>
      <h1>{row.title}</h1>
      <div className="row" style={{ marginBottom: 12 }}>
        <span className="chip">{row.status.replace(/_/g, " ")}</span>
        <RiskBadges risk={row.risk} flags={row.risk_flags} />
        {row.status === "awaiting_approval" && <Link className="btn primary" to={`/studio/${id}`}>Open proposal studio</Link>}
      </div>
      <div className="grid2">
        <section className="card">
          <h2>Job spec</h2>
          <p className="muted">Budget: {job.budget?.type} ${job.budget?.min}-{job.budget?.max} · Connects {job.connects_cost}</p>
          <b>Requirements</b>
          <ul>{(spec.requirements ?? job.skills ?? []).map((r: string) => <li key={r}>{r}</li>)}</ul>
          {spec.deliverables?.length > 0 && <><b>Deliverables</b><ul>{spec.deliverables.map((x: string) => <li key={x}>{x}</li>)}</ul></>}
          {spec.hidden_needs?.length > 0 && <p className="muted">Hidden needs: {spec.hidden_needs.join(", ")}</p>}
          <details><summary>Original post (untrusted)</summary><pre>{job.description}</pre></details>
        </section>
        <section className="card">
          <h2>Risk report</h2>
          <p>Score <b>{a.risk?.score ?? "-"}</b></p>
          <p className="muted">{a.risk?.explanation}</p>
          {a.risk?.injection_text?.length > 0 && (
            <div className="banner">Planted instruction detected and ignored: <em>{a.risk.injection_text.join(" ")}</em></div>
          )}
        </section>
      </div>
      <section className="card">
        <h2>Requirement to evidence matrix</h2>
        <table className="responsive">
          <thead><tr><th>Requirement</th><th>Covered</th><th>Evidence</th></tr></thead>
          <tbody>
            {(a.fit?.matrix ?? []).map((m: any) => (
              <tr key={m.requirement}>
                <td>{m.requirement}</td>
                <td>{m.covered ? <span className="chip ok">yes</span> : <span className="chip bad">no</span>}</td>
                <td>{m.evidence_ids.map((e: string) => <span key={e} className="chip">{e}</span>)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="muted">Fit {a.fit?.score ?? "-"} - {(a.fit?.reasons ?? []).join("; ")}</p>
      </section>
      <div className="grid2">
        <section className="card">
          <h2>Bid or skip</h2>
          <p><b>{a.decision?.action ?? "-"}</b></p>
          <ul>{(a.decision?.reasons ?? []).map((r: string) => <li key={r}>{r}</li>)}</ul>
        </section>
        <section className="card">
          <h2>Price</h2>
          <p><b>{a.price ? `$${a.price.amount}` : "-"}</b> {a.price && !a.price.worth_it && <span className="chip bad">not worth the Connects</span>}</p>
          <p className="muted">{a.price?.rationale}</p>
        </section>
      </div>
      <section className="card">
        <h2>Agent runs</h2>
        {d.data.runs.length === 0 && <p className="muted">No runs yet.</p>}
        <ul>{d.data.runs.map((r) => <li key={r.run_id}><Link to={`/runs/${r.run_id}`}>{r.run_id}</Link> - {r.status} <span className="muted">trace {r.trace_id}</span></li>)}</ul>
      </section>
    </div>
  );
}
