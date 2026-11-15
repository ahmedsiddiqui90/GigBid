import { useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { BarChart3, Compass, Inbox, KanbanSquare, Lightbulb, LogOut, MessagesSquare, Settings, TriangleAlert } from "lucide-react";
import { api, Health } from "../lib/api/client";
import { useLoad } from "../lib/hooks";
import { useAuth } from "../lib/auth";
import { Tour } from "./Tour";

const SEEN = "gigbid.tourSeen";

export function Layout() {
  const { me, refresh } = useAuth();
  const nav = useNavigate();
  const health = useLoad<Health | null>(async () => (await api.GET("/api/health")).data ?? null, [], 10000);
  const pending = useLoad<unknown[]>(async () => ((await api.GET("/api/approvals")).data as unknown[]) ?? [], [], 10000);
  const [tour, setTour] = useState(false);
  const [fresh, setFresh] = useState(() => { try { return !localStorage.getItem(SEEN); } catch { return false; } });
  const down = health.data && !health.data.marketplace;
  const nPending = (pending.data ?? []).length;
  const logout = async () => { await api.POST("/api/auth/logout"); await refresh(); nav("/login"); };
  const openTour = () => { setTour(true); setFresh(false); try { localStorage.setItem(SEEN, "1"); } catch { /* private mode */ } };

  return (
    <div className="shell">
      <nav className="rail" aria-label="Main" data-tour="nav">
        <div className="brand"><span className="brand-mark"><Compass size={18} color="#fff" /></span><span className="brand-name">GigBid</span></div>
        <div className="nav-group">
          <span className="nav-label">Work</span>
          <NavLink to="/" end className="nav-link"><Inbox />Job inbox{nPending > 0 && <span className="nav-count" aria-label={`${nPending} awaiting approval`}>{nPending}</span>}</NavLink>
          <NavLink to="/pipeline" className="nav-link"><KanbanSquare />Pipeline</NavLink>
          <NavLink to="/messages" className="nav-link"><MessagesSquare />Messages</NavLink>
          <span className="nav-label">Insight</span>
          <NavLink to="/analytics" className="nav-link"><BarChart3 />Analytics</NavLink>
          <NavLink to="/settings" className="nav-link"><Settings />Settings</NavLink>
        </div>
        <div className="rail-foot">
          {health.data && (
            <div className="status-line" title={`Models: ${health.data.model_profile}`}>
              <span className={`dot ${down ? "down" : ""}`} />
              {down ? "Marketplace offline" : `Connected to ${health.data.marketplace_adapter === "gigsim" ? "GigSim" : "Upwork"}`}
            </div>
          )}
          <div className="rail-user">
            <span className="who" title={me?.email}>{me?.email}</span>
            <button className={`icon-btn tour-btn ${fresh ? "fresh" : ""}`} onClick={openTour} aria-label="Take the guided tour" title="Guided tour" data-tour="tour-button"><Lightbulb /></button>
            <button className="icon-btn" onClick={logout} aria-label="Sign out" title="Sign out"><LogOut /></button>
          </div>
        </div>
      </nav>
      <main className="main">
        {down && (
          <div className="banner" role="alert" data-testid="degraded-banner">
            <TriangleAlert size={18} />
            <div><b>Marketplace unavailable.</b> GigBid is in degraded mode: new jobs and sends are queued and resume automatically when the
              marketplace is back. Drafts and pending approvals are safe.</div>
          </div>
        )}
        <Outlet />
      </main>
      <Tour open={tour} onClose={() => setTour(false)} />
    </div>
  );
}
