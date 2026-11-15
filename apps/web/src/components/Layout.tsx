import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { api, Health } from "../lib/api/client";
import { useLoad } from "../lib/hooks";
import { useAuth } from "../lib/auth";

export function Layout() {
  const { me, refresh } = useAuth();
  const nav = useNavigate();
  const health = useLoad<Health | null>(async () => (await api.GET("/api/health")).data ?? null, [], 10000);
  const down = health.data && !health.data.marketplace;
  const logout = async () => {
    await api.POST("/api/auth/logout");
    await refresh();
    nav("/login");
  };
  return (
    <div className="shell">
      <nav className="nav" aria-label="Main">
        <div className="brand">GigBid</div>
        <NavLink to="/" end>Job inbox</NavLink>
        <NavLink to="/pipeline">Pipeline</NavLink>
        <NavLink to="/messages">Messages</NavLink>
        <NavLink to="/analytics">Analytics</NavLink>
        <NavLink to="/settings">Settings</NavLink>
        <div className="spacer" />
        <span className="muted" style={{ color: "#9fb3d1" }}>{me?.email}</span>
        <button onClick={logout}>Sign out</button>
      </nav>
      <main className="main">
        {down && (
          <div className="banner" role="alert" data-testid="degraded-banner">
            Marketplace unavailable. GigBid is in degraded mode: new jobs and sends are queued and resume
            automatically when the marketplace is back. Drafts and pending approvals are safe.
          </div>
        )}
        {health.data && (
          <p className="muted" style={{ marginTop: 0 }}>
            Marketplace: {health.data.marketplace_adapter} · models: {health.data.model_profile}
          </p>
        )}
        <Outlet />
      </main>
    </div>
  );
}
