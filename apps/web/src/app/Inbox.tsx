import { useState } from "react";
import { Link } from "react-router-dom";
import { api, JobRow, unwrap } from "../lib/api/client";
import { useLoad } from "../lib/hooks";

export function RiskBadges({ risk, flags }: { risk?: number | null; flags?: string[] }) {
  if (risk == null) return <span className="muted">-</span>;
  const cls = risk >= 0.6 ? "bad" : risk >= 0.3 ? "warn" : "ok";
  return (
    <span>
      <span className={`chip ${cls}`}>risk {risk.toFixed(2)}</span>
      {(flags ?? []).slice(0, 3).map((f) => <span key={f} className="chip">{f.replace(/_/g, " ")}</span>)}
    </span>
  );
}

export default function Inbox() {
  const [filter, setFilter] = useState("all");
  const jobs = useLoad<JobRow[]>(() => unwrap(api.GET("/api/jobs")), [], 8000);
  const pending = useLoad<{ id: number; ref_id: string }[]>(async () => (await api.GET("/api/approvals")).data as never ?? [], [], 8000);
  const rows = (jobs.data ?? []).filter((j) => filter === "all" || (filter === "pending" ? j.status === "awaiting_approval" : j.decision === filter));
  const skip = async (id: string) => { await api.POST("/api/jobs/{job_id}/skip", { params: { path: { job_id: id } } }); jobs.reload(); };
  const analyse = async (id: string) => { await api.POST("/api/jobs/{job_id}/analyse", { params: { path: { job_id: id } } }); jobs.reload(); };

  return (
    <div>
      <h1>Job inbox</h1>
      <div className="row" style={{ marginBottom: 10 }} role="group" aria-label="Filter">
        {["all", "pending", "bid", "watch", "skip"].map((f) => (
          <button key={f} className={filter === f ? "primary" : ""} onClick={() => setFilter(f)} aria-pressed={filter === f}>
            {f === "pending" ? `Awaiting approval (${(pending.data ?? []).length})` : f}
          </button>
        ))}
      </div>
      {jobs.loading && !jobs.data && <p role="status">Loading jobs…</p>}
      {jobs.error && <p className="error" role="alert">Could not load jobs: {jobs.error}</p>}
      {jobs.data && rows.length === 0 && (
        <p className="empty">No jobs here yet. The Scout runs your saved searches every 30 minutes; new jobs appear automatically.</p>
      )}
      {rows.length > 0 && (
        <div className="card" style={{ padding: 0 }}>
          <table className="responsive" data-testid="inbox-table">
            <thead><tr><th>Job</th><th>Fit</th><th>Risk</th><th>Recommendation</th><th>Price</th><th>Connects</th><th /></tr></thead>
            <tbody>
              {rows.map((j) => (
                <tr key={j.job_id}>
                  <td><Link to={`/jobs/${j.job_id}`}>{j.title}</Link><div className="muted">{j.category} · {j.status.replace(/_/g, " ")}</div></td>
                  <td>{j.fit != null ? j.fit.toFixed(2) : "-"}</td>
                  <td><RiskBadges risk={j.risk} flags={j.risk_flags} /></td>
                  <td>{j.decision ? <span className={`chip ${j.decision === "bid" ? "ok" : j.decision === "skip" ? "bad" : "warn"}`}>{j.decision}</span> : "-"}</td>
                  <td>{j.price ? `$${j.price}` : "-"}</td>
                  <td>{j.connects ?? "-"}</td>
                  <td className="row">
                    {j.status === "awaiting_approval" && <Link className="btn primary" to={`/studio/${j.job_id}`}>Review</Link>}
                    {["queued", "skipped", "watch", "dead_letter", "waiting_marketplace", "needs_attention"].includes(j.status) && (
                      <button onClick={() => analyse(j.job_id)}>Analyse</button>
                    )}
                    {j.status !== "skipped" && j.status !== "submitted" && <button onClick={() => skip(j.job_id)}>Skip</button>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
