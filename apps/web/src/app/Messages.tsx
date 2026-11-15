import { useState } from "react";
import { api } from "../lib/api/client";
import { useLoad } from "../lib/hooks";

type Thread = {
  thread_id: string; job_id: string; messages: { from: string; text: string }[];
  pending_approval: { id: number; reply: string; intent: string; slots: { start: string }[] } | null;
};

function ThreadCard({ t, reload }: { t: Thread; reload: () => void }) {
  const pa = t.pending_approval;
  const [text, setText] = useState(pa?.reply ?? "");
  const [reason, setReason] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const act = async (action: "approve" | "edit" | "reject") => {
    if (!pa) return;
    if (action === "reject" && !reason.trim()) { setMsg("Add a reason to reject."); return; }
    await api.POST("/api/approvals/{approval_id}/resolve", { params: { path: { approval_id: pa.id } },
      body: action === "edit" ? { action, text } : action === "reject" ? { action, reason } : { action } });
    setMsg(action === "reject" ? "Rejected, nothing sent." : "Approved, sending…");
    setTimeout(reload, 2500);
  };
  const draft = async () => {
    await api.POST("/api/messages/{thread_id}/draft", { params: { path: { thread_id: t.thread_id } } });
    setMsg("Drafting a reply…");
    setTimeout(reload, 4000);
  };
  return (
    <section className="card">
      <h2>{t.job_id}</h2>
      {t.messages.map((m, i) => (
        <p key={i}><b>{m.from === "client" ? "Client" : "You"}:</b> {m.text}</p>
      ))}
      {pa ? (
        <div>
          <p>Suggested reply <span className={`chip ${pa.intent === "scam_signal" ? "bad" : ""}`}>{pa.intent.replace(/_/g, " ")}</span></p>
          <textarea style={{ minHeight: 110 }} aria-label="Reply editor" value={text} onChange={(e) => setText(e.target.value)} />
          <label><span>Reason (to reject)</span><input value={reason} onChange={(e) => setReason(e.target.value)} /></label>
          <div className="row">
            <button className="primary" onClick={() => act(text !== pa.reply ? "edit" : "approve")}>Approve and send</button>
            <button className="danger" onClick={() => act("reject")}>Reject</button>
          </div>
        </div>
      ) : (
        t.messages[t.messages.length - 1]?.from === "client" && <button onClick={draft}>Draft a reply</button>
      )}
      {msg && <p role="status">{msg}</p>}
    </section>
  );
}

export default function Messages() {
  const th = useLoad<{ threads: Thread[]; marketplace_unavailable: boolean }>(async () => (await api.GET("/api/messages")).data as never, [], 10000);
  if (th.error) return <p className="error" role="alert">{th.error}</p>;
  if (!th.data) return <p role="status">Loading…</p>;
  return (
    <div>
      <h1>Messages</h1>
      {th.data.marketplace_unavailable && <div className="banner" role="alert">Marketplace unavailable - messages will load when it is back.</div>}
      {th.data.threads.length === 0 && <p className="empty">No client conversations yet. They appear when a client replies to a proposal.</p>}
      {th.data.threads.map((t) => <ThreadCard key={t.thread_id + (t.pending_approval?.id ?? "")} t={t} reload={th.reload} />)}
    </div>
  );
}
