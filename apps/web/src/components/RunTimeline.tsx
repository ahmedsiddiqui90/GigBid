import { useEffect, useState } from "react";

type Ev = { node?: string; phase?: string; latency_s?: number; status?: string; summary?: string; type?: string };

/** Live node-by-node progress streamed from LangGraph over Server-Sent Events. */
export function RunTimeline({ runId }: { runId: string }) {
  const [events, setEvents] = useState<Ev[]>([]);
  const [status, setStatus] = useState("connecting");
  useEffect(() => {
    const es = new EventSource(`/api/runs/${runId}/stream`, { withCredentials: true });
    const add = (e: MessageEvent) => setEvents((xs) => [...xs, JSON.parse(e.data)]);
    es.addEventListener("node", add);
    es.addEventListener("run", (e) => {
      const d = JSON.parse((e as MessageEvent).data);
      setStatus(d.status);
      if (d.status !== "running") es.close();
    });
    es.onerror = () => {
      setStatus((s) => (s === "connecting" ? "finished (see steps below)" : s));
      es.close();
    };
    return () => es.close();
  }, [runId]);
  const ends = events.filter((e) => e.phase === "end");
  const running = events
    .filter((e) => e.phase === "start" && !ends.some((x) => x.node === e.node))
    .map((e) => e.node);
  return (
    <div aria-live="polite">
      <p>Status: <b>{status}</b></p>
      <ol className="timeline">
        {ends.map((e, i) => (
          <li key={i} className="done">
            ✓ {e.node} {e.latency_s !== undefined && <span className="muted">({e.latency_s}s)</span>}{" "}
            {e.summary && <span className="muted">{e.summary}</span>}
          </li>
        ))}
        {running.map((n, i) => (
          <li key={`r${i}`} className="running">… {n} running</li>
        ))}
      </ol>
    </div>
  );
}
