import { useState } from "react";
import { Link } from "react-router-dom";
import { Inbox as InboxIcon, RefreshCw, ShieldAlert, ShieldCheck } from "lucide-react";
import { api, JobRow, unwrap } from "../lib/api/client";
import { useLoad } from "../lib/hooks";

export function RiskBadges({ risk, flags }: { risk?: number | null; flags?: string[] }) {
  if (risk == null) return <span className="muted">Not assessed</span>;
  const cls = risk >= 0.6 ? "bad" : risk >= 0.3 ? "warn" : "ok";
  const label = risk >= 0.6 ? "High risk" : risk >= 0.3 ? "Some risk" : "Low risk";
  return (
    <span>
      <span className={`chip ${cls}`}>{risk >= 0.3 ? <ShieldAlert /> : <ShieldCheck />}{label} · {risk.toFixed(2)}</span>
      {(flags ?? []).slice(0, 2).map((f) => <span key={f} className="chip">{f.replace(/_/g, " ")}</span>)}
    </span>
  );
}

export function FitMeter({ fit }: { fit?: number | null }) {
  if (fit == null) return <span className="muted">-</span>;
  return (
    <span className="meter" aria-label={`fit ${Math.round(fit * 100)} percent`}>
      <span className="bar"><span style={{ width: `${Math.round(fit * 100)}%` }} /></span><b className="num">{Math.round(fit * 100)}%</b>
    </span>
  );
}

const DECISION: Record<string, { label: string; cls: string }> = {
  bid: { label: "Bid", cls: "ok" }, watch: { label: "Watch", cls: "warn" }, skip: { label: "Skip", cls: "bad" },
};
const STATUS: Record<string, string> = {
  queued: "Queued", analysing: "Analysing…", awaiting_approval: "Awaiting your approval", submitted: "Submitted", skipped: "Skipped",
  watch: "Watching", resuming: "Submitting…", waiting_marketplace: "Waiting for marketplace", needs_attention: "Needs attention",
  dead_letter: "Failed", rejected: "Rejected", blocked: "Blocked by compliance",
};

export default function Inbox() {
  const [filter, setFilter] = useState("all");
  const jobs = useLoad<JobRow[]>(() => unwrap(api.GET("/api/jobs")), [], 8000);
  const all = jobs.data ?? [];
  const tabs = [
    { key: "all", label: "All", n: all.length },
    { key: "pending", label: "Awaiting approval", n: all.filter((j) => j.status === "awaiting_approval").length },
    { key: "bid", label: "Bid", n: all.filter((j) => j.decision === "bid").length },
    { key: "watch", label: "Watch", n: all.filter((j) => j.decision === "watch").length },
    { key: "skip", label: "Skipped", n: all.filter((j) => j.decision === "skip").length },
  ];
  const rows = all.filter((j) => filter === "all" || (filter === "pending" ? j.status === "awaiting_approval" : j.decision === filter));
  const firstReview = rows.findIndex((j) => j.status === "awaiting_approval");
  const skip = async (id: string) => { await api.POST("/api/jobs/{job_id}/skip", { params: { path: { job_id: id } } }); jobs.reload(); };
  const analyse = async (id: string) => { await api.POST("/api/jobs/{job_id}/analyse", { params: { path: { job_id: id } } }); jobs.reload(); };

  return (
    <div>
      <div className="page-head">
        <div>
          <h1>Job inbox</h1>
          <p className="page-sub">New jobs from your saved searches, ranked by how well your portfolio fits. Review drafts before anything is sent.</p>
        </div>
        <button onClick={() => jobs.reload()} aria-label="Refresh inbox"><RefreshCw />Refresh</button>
      </div>
      <div className="seg" role="group" aria-label="Filter jobs" data-tour="inbox-filters" style={{ marginBottom: 16 }}>
        {tabs.map((t) => (
          <button key={t.key} aria-pressed={filter === t.key} onClick={() => setFilter(t.key)}>
            {t.label} <span className="count num">{t.n}</span>
          </button>
        ))}
      </div>
      {jobs.loading && !jobs.data && (
        <div className="card stack" role="status" aria-label="Loading jobs">{[0, 1, 2, 3].map((k) => <div key={k} className="skeleton" />)}</div>
      )}
      {jobs.error && <div className="banner" role="alert">Could not load jobs: {jobs.error}. Check your connection and refresh.</div>}
      {jobs.data && rows.length === 0 && (
        <div className="card empty">
          <InboxIcon />
          <b>{filter === "all" ? "No jobs yet" : "Nothing in this view"}</b>
          <span>{filter === "all" ? "The Scout runs your saved searches every 30 minutes; new jobs appear here automatically." : "Try another filter."}</span>
        </div>
      )}
      {rows.length > 0 && (
        <div className="card flush" data-tour="inbox-table">
          <table className="responsive" data-testid="inbox-table">
            <thead><tr><th>Job</th><th>Fit</th><th>Risk</th><th>Recommendation</th><th className="num">Price</th><th className="num">Connects</th><th><span className="sr-only">Actions</span></th></tr></thead>
            <tbody>
              {rows.map((j, idx) => {
                const d = j.decision ? DECISION[j.decision] : null;
                return (
                  <tr key={j.job_id}>
                    <td style={{ maxWidth: 340 }}>
                      <Link className="job-title" to={`/jobs/${j.job_id}`}>{j.title}</Link>
                      <div className="muted small">{(j.category ?? "other").replace(/_/g, " ")} · {STATUS[j.status] ?? j.status.replace(/_/g, " ")}</div>
                    </td>
                    <td><FitMeter fit={j.fit} /></td>
                    <td><RiskBadges risk={j.risk} flags={j.risk_flags} /></td>
                    <td>{d ? <span className={`chip ${d.cls}`}>{d.label}</span> : <span className="muted">-</span>}</td>
                    <td className="num">{j.price ? `$${j.price.toLocaleString()}` : "-"}</td>
                    <td className="num">{j.connects ?? "-"}</td>
                    <td>
                      <div className="row" style={{ justifyContent: "flex-end", flexWrap: "nowrap" }}>
                        {j.status === "awaiting_approval" && (
                          <Link className="btn primary" to={`/studio/${j.job_id}`} data-tour={idx === firstReview ? "review-action" : undefined}>Review</Link>
                        )}
                        {["queued", "skipped", "watch", "dead_letter", "waiting_marketplace", "needs_attention"].includes(j.status) && (
                          <button onClick={() => analyse(j.job_id)}>Analyse</button>
                        )}
                        {j.status !== "skipped" && j.status !== "submitted" && <button className="ghost" onClick={() => skip(j.job_id)}>Skip</button>}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
