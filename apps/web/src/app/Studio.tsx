import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, Check, CircleCheck, CircleX, Pencil, ShieldCheck, Sparkles, X } from "lucide-react";
import { EvidenceText } from "../components/EvidenceText";
import { api, unwrap } from "../lib/api/client";
import { useLoad } from "../lib/hooks";

type Approval = {
  id: number; status: string; thread_id: string;
  payload: {
    job_title: string; draft: { cover_letter: string; screening_answers: string[]; cited_ids: string[] };
    evidence: Record<string, any>; claims: { claim: string; label: string; reason?: string }[];
    risk: { score: number; flags: string[]; injection_text?: string[] }; price: { amount: number; rationale: string; connects_cost: number };
    critique: { score: number; passed: boolean; issues: string[] }; compliance: { passed: boolean; edits: string[]; reason?: string };
    preview: { status?: string; would_send?: Record<string, any>; connects_cost?: number; connects_balance_after?: number | null; detail?: any };
    strategy?: string;
  };
};

export default function Studio() {
  const { id = "" } = useParams();
  const nav = useNavigate();
  const [text, setText] = useState("");
  const [answers, setAnswers] = useState<string[]>([]);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const appr = useLoad<Approval | null>(async () => {
    const d: any = await unwrap(api.GET("/api/jobs/{job_id}", { params: { path: { job_id: id } } }));
    if (!d.approval) return null;
    return (await unwrap(api.GET("/api/approvals/{approval_id}", { params: { path: { approval_id: d.approval.id } } }))) as Approval;
  }, [id]);

  useEffect(() => {
    if (appr.data) { setText(appr.data.payload.draft.cover_letter); setAnswers(appr.data.payload.draft.screening_answers ?? []); }
  }, [appr.data]);

  if (appr.loading) return <div className="card stack" role="status">{[0, 1, 2].map((k) => <div key={k} className="skeleton" />)}</div>;
  if (appr.error) return <div className="banner" role="alert">{appr.error}</div>;
  if (!appr.data) return <div className="card empty"><b>No draft is waiting for this job.</b><Link to={`/jobs/${id}`}>Back to the job</Link></div>;
  const a = appr.data;
  const p = a.payload;
  const pending = a.status === "pending";
  const edited = text !== p.draft.cover_letter || JSON.stringify(answers) !== JSON.stringify(p.draft.screening_answers ?? []);
  const supported = p.claims.filter((c) => c.label === "supported").length;
  const words = text.trim().split(/\s+/).filter(Boolean).length;

  const resolve = async (action: "approve" | "edit" | "reject") => {
    if (action === "reject" && !reason.trim()) { setMsg("Give a reason for rejecting (it helps GigBid learn)."); return; }
    setBusy(true);
    const body = action === "edit" ? { action, text, answers } : action === "reject" ? { action, reason } : { action };
    const res = await api.POST("/api/approvals/{approval_id}/resolve", { params: { path: { approval_id: a.id } }, body });
    setBusy(false);
    if (res.error) { setMsg("Could not send your decision. Try again."); return; }
    setMsg(action === "reject" ? "Rejected. Nothing was sent." : "Approved. Submitting through the marketplace…");
    setTimeout(() => nav(`/jobs/${id}`), 1200);
  };

  const regenerate = async (i: number) => {
    const paras = text.split(/\n\n+/);
    const res: any = await api.POST("/api/jobs/{job_id}/regenerate", { params: { path: { job_id: id } }, body: { paragraph: paras[i], instruction: "Make it more specific to the client." } });
    if (res.data?.paragraph) { paras[i] = res.data.paragraph; setText(paras.join("\n\n")); setEditing(true); }
  };

  return (
    <div>
      <Link to={`/jobs/${id}`} className="muted small" style={{ display: "inline-flex", gap: 6, alignItems: "center", textDecoration: "none" }}><ArrowLeft size={15} />Job details</Link>
      <div className="page-head" style={{ marginTop: 8 }}>
        <div>
          <h1>{p.job_title}</h1>
          <p className="page-sub">Read the draft, check the evidence behind each claim, then approve, edit or reject. Nothing is sent until you decide.</p>
        </div>
        <div className="row">
          <span className="chip accent"><Sparkles />{p.strategy === "question_first" ? "Question-first opening" : "Evidence-first opening"}</span>
          <span className="chip">{words} words</span>
        </div>
      </div>
      {!pending && <div className="banner info">This draft was already {a.status}. It is shown read-only.</div>}

      <div className="grid2 studio-grid">
        <section className="card" style={{ marginBottom: 0 }}>
          <div className="card-head">
            <h2>Proposal</h2>
            {pending && <button className="ghost" onClick={() => setEditing(!editing)} aria-pressed={editing}><Pencil />{editing ? "Preview" : "Edit"}</button>}
          </div>
          {editing ? (
            <>
              <label><span>Cover letter</span>
                <textarea aria-label="Cover letter editor" data-testid="draft-editor" value={text} onChange={(e) => setText(e.target.value)} disabled={!pending} />
              </label>
              {answers.map((x, i) => (
                <label key={i}><span>Screening answer {i + 1}</span>
                  <textarea style={{ minHeight: 90 }} value={x} onChange={(e) => setAnswers(answers.map((y, j) => (j === i ? e.target.value : y)))} disabled={!pending} />
                </label>
              ))}
              <div className="row">
                {text.split(/\n\n+/).map((_, i) => <button key={i} onClick={() => regenerate(i)} disabled={!pending}><Sparkles />Rewrite paragraph {i + 1}</button>)}
              </div>
            </>
          ) : (
            <>
              <p className="muted small" style={{ marginTop: -4 }}>Hover or focus a highlighted citation to see the portfolio evidence behind the claim.</p>
              <EvidenceText text={text} evidence={p.evidence} claims={p.claims} />
              {answers.length > 0 && (<><h3>Screening answers</h3>{answers.map((x, i) => <EvidenceText key={i} text={x} evidence={p.evidence} />)}</>)}
            </>
          )}
        </section>

        <div className="stack">
          <section className="card" style={{ marginBottom: 0 }} data-testid="dry-run">
            <h2>What will be sent</h2>
            <dl className="kv">
              <dt>Bid</dt><dd className="big num">${p.price?.amount?.toLocaleString()}</dd>
              <dt>Connects</dt><dd className="num">Connects cost {p.preview?.connects_cost ?? p.price?.connects_cost}{p.preview?.connects_balance_after != null && <span className="muted"> · {p.preview.connects_balance_after} left after</span>}</dd>
            </dl>
            <p className="muted small" style={{ marginBottom: 0 }}>{p.price?.rationale}</p>
            {p.preview?.status === "unavailable" && <p className="error small">Marketplace unavailable: the preview could not be generated.</p>}
          </section>
          <section className="card" style={{ marginBottom: 0 }}>
            <h2>Checks</h2>
            <div className="row" style={{ marginBottom: 10 }}>
              <span className="chip ok"><CircleCheck />{supported}/{p.claims.length} claims supported</span>
              <span className={`chip ${p.critique?.passed ? "ok" : "warn"}`}>Critic {Math.round((p.critique?.score ?? 0) * 100)}%</span>
              <span className={`chip ${p.compliance?.passed ? "ok" : "bad"}`}><ShieldCheck />{p.compliance?.passed ? "Policy OK" : "Blocked"}</span>
            </div>
            {(p.critique?.issues ?? []).length > 0 && (<><h3>Critic notes</h3><ul className="small" style={{ paddingLeft: 18, margin: 0 }}>{p.critique.issues.map((x) => <li key={x}>{x}</li>)}</ul></>)}
            {(p.compliance?.edits ?? []).length > 0 && (<><h3>Compliance edits</h3><ul className="small muted" style={{ paddingLeft: 18, margin: 0 }}>{p.compliance.edits.map((x, i) => <li key={i}>{x}</li>)}</ul></>)}
            {p.risk?.injection_text && p.risk.injection_text.length > 0 && <p className="chip warn" style={{ marginTop: 10 }}>Instruction planted in the job post was ignored</p>}
          </section>
        </div>
      </div>

      {pending && (
        <div className="actionbar" style={{ marginTop: 18 }}>
          {edited && <span className="chip warn wrap"><Pencil />You edited the draft: Compliance re-checks it and your edits feed style memory.</span>}
          <label><span>Reason (required to reject)</span><input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. budget too low for this scope" /></label>
          <button className="danger" disabled={busy} onClick={() => resolve("reject")}><X />Reject</button>
          <button className="primary" disabled={busy} onClick={() => resolve(edited ? "edit" : "approve")}>
            <Check />{edited ? "Approve with my edits" : "Approve and submit"}
          </button>
          {msg && <p role="status" className="small" style={{ width: "100%", margin: 0 }}>{msg.startsWith("Rejected") ? <CircleX size={14} /> : null} {msg}</p>}
        </div>
      )}
    </div>
  );
}
