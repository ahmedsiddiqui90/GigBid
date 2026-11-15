import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../lib/api/client";
import { useAuth } from "../lib/auth";

const PERSONAS = [
  { id: "ai_ml", label: "AI/ML engineer (synthetic persona)", rate: 45, floor: 35, cat: "ai_ml" },
  { id: "fullstack", label: "Full-stack web developer (synthetic persona)", rate: 40, floor: 30, cat: "web_dev" },
  { id: "data_analyst", label: "Data analyst (synthetic persona)", rate: 35, floor: 25, cat: "data_analysis" },
] as const;

export default function Onboarding() {
  const [persona, setPersona] = useState<(typeof PERSONAS)[number]["id"]>("ai_ml");
  const p = PERSONAS.find((x) => x.id === persona)!;
  const [rate, setRate] = useState<number>(p.rate);
  const [floor, setFloor] = useState<number>(p.floor);
  const [connects, setConnects] = useState(80);
  const [query, setQuery] = useState("");
  const [marketplace, setMarketplace] = useState<"gigsim" | "upwork_live">("gigsim");
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const { refresh } = useAuth();
  const nav = useNavigate();

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    const res = await api.POST("/api/onboarding", {
      body: { persona_id: persona, marketplace, hourly_rate: rate, floor_rate: floor, weekly_connects: connects,
        search_query: query, search_category: p.cat, every_minutes: 30 },
    });
    if (res.error) { setError("Could not save. Check the values."); setBusy(false); return; }
    if (file) {
      const fd = new FormData();
      fd.append("file", file);
      await fetch("/api/onboarding/upload", { method: "POST", body: fd, credentials: "include" });
    }
    if (marketplace === "upwork_live") window.location.href = "/api/onboarding/upwork/start";
    await refresh();
    nav("/");
  };

  return (
    <div style={{ maxWidth: 560, margin: "40px auto" }} className="pad">
      <h1>Set up GigBid</h1>
      <p className="page-sub" style={{ marginBottom: 20 }}>Pick the profile GigBid writes for, your rates and what to search for. You can change all of this later in Settings.</p>
      <form className="card" onSubmit={submit} aria-label="Onboarding">
        <label><span>Profile</span>
          <select value={persona} onChange={(e) => {
            const np = PERSONAS.find((x) => x.id === e.target.value)!;
            setPersona(np.id); setRate(np.rate); setFloor(np.floor);
          }}>
            {PERSONAS.map((x) => <option key={x.id} value={x.id}>{x.label}</option>)}
          </select>
        </label>
        <label><span>Marketplace</span>
          <select value={marketplace} onChange={(e) => setMarketplace(e.target.value as "gigsim" | "upwork_live")}>
            <option value="gigsim">GigSim (simulator)</option>
            <option value="upwork_live">Upwork (live, OAuth - drafts only, you confirm on Upwork)</option>
          </select>
        </label>
        <div className="grid2">
          <label><span>Hourly rate (USD)</span><input type="number" min={1} value={rate} onChange={(e) => setRate(+e.target.value)} /></label>
          <label><span>Floor rate (USD)</span><input type="number" min={1} value={floor} onChange={(e) => setFloor(+e.target.value)} /></label>
        </div>
        <label><span>Weekly Connects budget</span><input type="number" min={0} value={connects} onChange={(e) => setConnects(+e.target.value)} /></label>
        <label><span>Saved search keywords (empty = everything in your category)</span><input value={query} onChange={(e) => setQuery(e.target.value)} /></label>
        <label><span>Add to your portfolio (PDF CV, Markdown case study, proposals JSON) - optional</span>
          <input type="file" accept=".pdf,.md,.txt,.json" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        </label>
        {error && <p className="error" role="alert">{error}</p>}
        <button className="primary" disabled={busy} type="submit">Start finding jobs</button>
      </form>
    </div>
  );
}
