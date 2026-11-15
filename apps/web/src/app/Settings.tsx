import { useState } from "react";
import { api } from "../lib/api/client";
import { useLoad } from "../lib/hooks";

type S = { settings: Record<string, any>; persona_id: string; marketplace: string; saved_searches: { id: number; query: string; category: string | null; every_minutes: number; last_run: string | null }[]; connected_accounts: string[] };
type Mem = { style: { key: string; rule: string; count: number; promotion_rule: string }[]; style_candidates: { key: string; count: number }[]; outcome: { key: string; submitted: number; replied: number; hired: number }[] };

export default function Settings() {
  const s = useLoad<S>(async () => (await api.GET("/api/settings")).data as never);
  const m = useLoad<Mem>(async () => (await api.GET("/api/memory")).data as never);
  const [q, setQ] = useState("");
  const [saved, setSaved] = useState<string | null>(null);
  if (!s.data) return <p role="status">Loading…</p>;
  const st = s.data.settings;
  const save = async (patch: Record<string, any>) => {
    await api.PUT("/api/settings", { body: { ...st, ...patch } as never });
    setSaved("Saved");
    s.reload();
  };
  const forget = async (ns: string, key: string) => { await api.DELETE("/api/memory/{ns}/{key}", { params: { path: { ns, key } } }); m.reload(); };
  return (
    <div>
      <h1>Settings</h1>
      <div className="grid2">
        <section className="card"><h2>Autonomy and budgets</h2>
          <label><span>Autonomy</span>
            <select value={st.autonomy ?? "auto_skip_low_fit"} onChange={(e) => save({ autonomy: e.target.value })}>
              <option value="manual">Manual: I review every job</option>
              <option value="auto_skip_low_fit">Auto-skip low-fit jobs (never auto-send)</option>
            </select>
          </label>
          <label><span>Weekly Connects budget</span><input type="number" defaultValue={st.weekly_connects} onBlur={(e) => save({ weekly_connects: +e.target.value })} /></label>
          <label><span>Hourly / floor rate</span>
            <div className="row"><input type="number" defaultValue={st.hourly_rate} onBlur={(e) => save({ hourly_rate: +e.target.value })} style={{ width: 120 }} />
              <input type="number" defaultValue={st.floor_rate} onBlur={(e) => save({ floor_rate: +e.target.value })} style={{ width: 120 }} /></div>
          </label>
          {saved && <p role="status" className="muted">{saved}</p>}
        </section>
        <section className="card"><h2>Accounts and searches</h2>
          <p>Profile: <b>{s.data.persona_id}</b> · marketplace <b>{s.data.marketplace}</b></p>
          <p>Connected: {s.data.connected_accounts.map((c) => <span className="chip ok" key={c}>{c}</span>)}</p>
          <a className="btn" href="/api/onboarding/upwork/start">Connect Upwork (OAuth)</a>
          <ul>{s.data.saved_searches.map((x) => (
            <li key={x.id}>"{x.query || "(all)"}" in {x.category ?? "any"} every {x.every_minutes} min
              <button onClick={async () => { await api.DELETE("/api/saved-searches/{sid}", { params: { path: { sid: x.id } } }); s.reload(); }}>Remove</button></li>
          ))}</ul>
          <div className="row"><input placeholder="new search keywords" value={q} onChange={(e) => setQ(e.target.value)} style={{ flex: 1 }} />
            <button onClick={async () => { await api.POST("/api/saved-searches", { body: { query: q, every_minutes: 30 } }); setQ(""); s.reload(); }}>Add</button></div>
        </section>
      </div>
      <section className="card" data-testid="memory-viewer"><h2>What GigBid has learned</h2>
        <p className="muted">Style rules are promoted only after the same edit pattern appears in at least two of your edits. Outcome memory comes only from confirmed marketplace events.</p>
        <h3>Style rules</h3>
        {(m.data?.style ?? []).length === 0 && <p className="muted">None yet.</p>}
        <ul>{(m.data?.style ?? []).map((x) => <li key={x.key}>{x.rule} <span className="muted">(seen {x.count}x; {x.promotion_rule})</span> <button onClick={() => forget("style", x.key)}>Delete</button></li>)}</ul>
        <h3>Candidate patterns (not yet used)</h3>
        <ul>{(m.data?.style_candidates ?? []).map((x) => <li key={x.key}>{x.key} - seen {x.count}x <button onClick={() => forget("style_candidates", x.key)}>Delete</button></li>)}</ul>
        <h3>Outcome memory</h3>
        <ul>{(m.data?.outcome ?? []).map((x) => <li key={x.key}>{x.key}: {x.replied}/{x.submitted} replied, {x.hired} hired <button onClick={() => forget("outcome", x.key)}>Delete</button></li>)}</ul>
      </section>
    </div>
  );
}
