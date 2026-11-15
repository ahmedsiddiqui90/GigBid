import { Link } from "react-router-dom";
import { api, unwrap } from "../lib/api/client";
import { useLoad } from "../lib/hooks";

type Board = { stages: string[]; columns: Record<string, { job_id: string; title: string; price?: number }[]> };

export default function Pipeline() {
  const b = useLoad<Board>(() => unwrap(api.GET("/api/pipeline")) as Promise<Board>, [], 8000);
  if (b.error) return <p className="error" role="alert">{b.error}</p>;
  if (!b.data) return <p role="status">Loading…</p>;
  return (
    <div>
<div className="page-head"><div><h1>Pipeline</h1><p className="page-sub">Submitted proposals move across the board automatically as the marketplace reports views, replies, interviews and hires.</p></div></div>
      <div className="kanban" data-tour="pipeline">
        {b.data.stages.map((s) => (
          <div key={s} className="col" aria-label={`${s} column`}>
            <h3>{s} ({b.data!.columns[s]?.length ?? 0})</h3>
            {(b.data!.columns[s] ?? []).map((c) => (
              <div className="kcard" key={c.job_id}><Link to={`/jobs/${c.job_id}`}>{c.title}</Link>{c.price ? <div className="muted">${c.price}</div> : null}</div>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}
