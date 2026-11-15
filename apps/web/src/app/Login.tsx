import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Compass, FileCheck2, ShieldCheck, UserCheck } from "lucide-react";
import { api } from "../lib/api/client";
import { useAuth } from "../lib/auth";

export default function Login() {
  const [mode, setMode] = useState<"login" | "signup">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const { refresh } = useAuth();
  const nav = useNavigate();

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const res = mode === "login"
      ? await api.POST("/api/auth/login", { body: { email, password } })
      : await api.POST("/api/auth/signup", { body: { email, password, name } });
    setBusy(false);
    if (res.error || !res.data) {
      const d = (res.error as { detail?: unknown })?.detail;
      setError(typeof d === "string" ? d : "Check your email and password (at least 8 characters).");
      return;
    }
    await refresh();
    nav(res.data.onboarded ? "/" : "/onboarding");
  };

  return (
    <div className="auth">
      <aside className="auth-side">
        <div className="brand" style={{ padding: 0 }}><span className="brand-mark"><Compass size={18} color="#fff" /></span><span className="brand-name">GigBid</span></div>
        <div>
          <h1>Win the right freelance work, without the busywork.</h1>
          <p>GigBid scouts jobs, checks them for scams and fit, and drafts proposals where every claim points to your real portfolio.</p>
          <ul className="auth-points">
            <li><ShieldCheck /><span>Scams, free-work requests and planted instructions are caught before you spend a Connect.</span></li>
            <li><FileCheck2 /><span>Every sentence about your experience is checked against your portfolio evidence.</span></li>
            <li><UserCheck /><span>Nothing is sent until you approve it.</span></li>
          </ul>
        </div>
        <p className="small" style={{ color: "var(--rail-muted)" }}>AI-4016 · runs on open-weight models</p>
      </aside>
      <main className="auth-main">
        <div className="auth-card">
          <h1 style={{ fontSize: 26 }}>{mode === "login" ? "Sign in" : "Create your account"}</h1>
          <p className="page-sub" style={{ marginBottom: 22 }}>{mode === "login" ? "Welcome back. Your drafts are waiting." : "Takes a minute; you'll pick a profile next."}</p>
          <form onSubmit={submit} aria-label={mode === "login" ? "Sign in" : "Create account"}>
            {mode === "signup" && <label><span>Name</span><input value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" /></label>}
            <label><span>Email</span><input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" /></label>
            <label><span>Password</span><input type="password" required minLength={8} value={password} onChange={(e) => setPassword(e.target.value)}
              autoComplete={mode === "login" ? "current-password" : "new-password"} /></label>
            {error && <p className="error small" role="alert">{error}</p>}
            <button className="primary" disabled={busy} type="submit" style={{ width: "100%", justifyContent: "center", padding: "10px 14px" }}>
              {busy ? "Please wait…" : mode === "login" ? "Sign in" : "Create account"}
            </button>
          </form>
          <p className="muted small" style={{ marginTop: 18, textAlign: "center" }}>
            {mode === "login" ? "New to GigBid? " : "Already have an account? "}
            <button className="ghost" style={{ padding: 0, color: "var(--accent)", display: "inline" }} onClick={() => setMode(mode === "login" ? "signup" : "login")}>
              {mode === "login" ? "Create an account" : "Sign in"}
            </button>
          </p>
        </div>
      </main>
    </div>
  );
}
