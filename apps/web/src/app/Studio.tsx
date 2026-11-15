import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
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
  const [msg, setMsg] = useState<string | null>(null);
  const appr = useLoad<Approval | null>(async () => {
    const d: any = await unwrap(api.GET("/api/jobs/{job_id}", { params: { path: { job_id: id } } }));
    if (!d.approval) return null;
    return (await unwrap(api.GET("/api/approvals/{approval_id}", { params: { path: { approval_id: d.approval.id } } }))) as Approval;
  }, [id]);

  useEffect(() => {
    if (appr.data) {
      setText(appr.data.payload.draft.cover_letter);
      setAnswers(appr.data.payload.draft.screening_answers ?? []);
    }
  }, [appr.data]);

  if (appr.loading) return <p role="status">Loading draft…</p>;
  if (appr.error) return <p className="error" role="alert">{appr.error}</p>;
  if (!appr.data) return <p className="empty">No draft waiting for approval for this job. <Link to={`/jobs/${id}`}>Back to the job</Link></p>;
  const a = appr.data;
  const p = a.payload;
  const pending = a.status === "pending";
  const edited = text !== p.draft.cover_letter || JSON.stringify(answers) !== JSON.stringify(p.draft.screening_answers ?? []);

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
    if (res.data?.paragraph) { paras[i] = res.data.paragraph; setText(paras.join("\n\n")); }
  };

  return (
    <div>
      <h1>Proposal studio - {p.job_title}</h1>
      {!pending && <div className="banner">This approval is {a.status}.</div>}
      <div className="grid2">
        <section className="card">
          <h2>Draft (hover a citation to see its evidence)</h2>
          <EvidenceText text={text} evidence={p.evidence} claims={p.claims} />
          {answers.length > 0 && (
            <>
              <h2 style={{ marginTop: 12 }}>Screening answers</h2>
              {answers.map((x, i) => <EvidenceText key={i} text={x} evidence={p.evidence} />)}
            </>
          )}
        </section>
        <section className="card">
          <h2>Edit</h2>
          <label><span>Cover letter</span>
            <textarea aria-label="Cover letter editor" data-testid="draft-editor" value={text} onChange={(e) => setText(e.target.value)} disabled={!pending} />
          </label>
          {answers.map((x, i) => (
            <label key={i}><span>Screening answer {i + 1}</span>
              <textarea style={{ minHeight: 80 }} value={x} onChange={(e) => setAnswers(answers.map((y, j) => (j === i ? e.target.value : y)))} disabled={!pending} />
            </label>
          ))}
          <div className="row">
            {text.split(/\n\n+/).map((_, i) => <button key={i} onClick={() => regenerate(i)} disabled={!pending}>Regenerate paragraph {i + 1}</button>)}
          </div>
        </section>
      </div>
      <div className="grid2">
        <section className="card">
          <h2>Critic and compliance</h2>
          <p>Critic score {p.critique?.score} {p.critique?.passed ? <span className="chip ok">passed</span> : <span className="chip warn">limit reached</span>}</p>
          <ul>{(p.critique?.issues ?? []).map((x) => <li key={x}>{x}</li>)}</ul>
          <p>Compliance {p.compliance?.passed ? <span className="chip ok">passed</span> : <span className="chip bad">blocked</span>} {p.compliance?.reason}</p>
          <ul>{(p.compliance?.edits ?? []).map((x, i) => <li key={i} className="muted">{x}</li>)}</ul>
          {p.risk?.injection_text && p.risk.injection_text.length > 0 && <p className="chip warn">Injected instruction in the post was ignored</p>}
          <p className="muted">A/B strategy: {p.strategy}</p>
        </section>
        <section className="card" data-testid="dry-run">
          <h2>What will be sent (dry run)</h2>
          <p>Bid <b>${p.price?.amount}</b> · Connects cost <b>{p.preview?.connects_cost ?? p.price?.connects_cost}</b>
            {p.preview?.connects_balance_after != null && <> · balance after {p.preview.connects_balance_after}</>}</p>
          <p className="muted">{p.price?.rationale}</p>
          {p.preview?.status === "unavailable" && <p className="error">Marketplace unavailable: preview could not be generated.</p>}
          {edited && <p className="chip warn">You edited the draft: it will be re-checked by Compliance and your edits feed style memory.</p>}
        </section>
      </div>
      <section className="card">
        <label><span>Reason (required to reject)</span><input value={reason} onChange={(e) => setReason(e.target.value)} disabled={!pending} /></label>
        {msg && <p role="status">{msg}</p>}
        <div className="row">
          <button className="primary" disabled={!pending || busy} onClick={() => resolve(edited ? "edit" : "approve")}>
            {edited ? "Approve with my edits" : "Approve and submit"}
          </button>
          <button className="danger" disabled={!pending || busy} onClick={() => resolve("reject")}>Reject</button>
        </div>
      </section>
    </div>
  );
}
