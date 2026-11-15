import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
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
      setError(typeof d === "string" ? d : "Check your email and password (8+ characters).");
      return;
    }
    await refresh();
    nav(res.data.onboarded ? "/" : "/onboarding");
  };

  return (
    <div style={{ maxWidth: 420, margin: "60px auto" }} className="pad">
      <h1>GigBid</h1>
      <p className="muted">Finds jobs, checks risk and writes evidence-backed proposals. Nothing is sent until you approve it.</p>
      <form className="card" onSubmit={submit} aria-label={mode === "login" ? "Sign in" : "Create account"}>
        {mode === "signup" && (
          <label><span>Name</span><input value={name} onChange={(e) => setName(e.target.value)} /></label>
        )}
        <label><span>Email</span><input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} /></label>
        <label><span>Password</span><input type="password" required minLength={8} value={password} onChange={(e) => setPassword(e.target.value)} /></label>
        {error && <p className="error" role="alert">{error}</p>}
        <div className="row">
          <button className="primary" disabled={busy} type="submit">{mode === "login" ? "Sign in" : "Create account"}</button>
          <button type="button" onClick={() => setMode(mode === "login" ? "signup" : "login")}>
            {mode === "login" ? "New here? Create an account" : "Have an account? Sign in"}
          </button>
        </div>
      </form>
    </div>
  );
}
