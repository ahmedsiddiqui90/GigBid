import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

/** Guided product tour: spotlights real elements (data-tour="...") and walks through the core workflow. */
type Step = { route: string; target: string; title: string; body: string };

export const TOUR_STEPS: Step[] = [
  { route: "/", target: "nav", title: "Welcome to GigBid", body: "GigBid finds jobs, checks them for risk and drafts proposals backed by your portfolio. Nothing is ever sent until you approve it. This tour takes about a minute." },
  { route: "/", target: "inbox-filters", title: "Your job inbox", body: "Jobs the Scout found, ranked by fit. Filter to what needs you now: drafts awaiting approval, recommended bids, jobs to watch, or skipped ones." },
  { route: "/", target: "inbox-table", title: "Fit, risk and the recommendation", body: "Each row shows how well your portfolio covers the job, risk flags from the client's history and the post, the suggested price and the Connects it costs. Open a job to see the reasoning." },
  { route: "/", target: "review-action", title: "Review before anything is sent", body: "Drafts wait here for you. Review opens the proposal studio, where every claim links to the evidence behind it." },
  { route: "/pipeline", target: "pipeline", title: "Pipeline", body: "Submitted proposals move across the board as the marketplace reports views, replies, interviews and hires." },
  { route: "/messages", target: "messages", title: "Client messages", body: "When a client replies, GigBid classifies the message, drafts an answer (with interview slots if asked) and waits for your approval again." },
  { route: "/settings", target: "memory", title: "What GigBid learns", body: "Your edits teach GigBid your style, but only once a pattern repeats. You can see and delete everything it has learned here." },
  { route: "/", target: "tour-button", title: "That's it", body: "Reopen this tour any time from the bulb in the sidebar." },
];

type Rect = { top: number; left: number; width: number; height: number };

export function Tour({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [i, setI] = useState(0);
  const [rect, setRect] = useState<Rect | null>(null);
  const nav = useNavigate();
  const loc = useLocation();
  const nextRef = useRef<HTMLButtonElement>(null);
  const step = TOUR_STEPS[i];

  useEffect(() => { if (open) setI(0); }, [open]);
  useEffect(() => { if (open && loc.pathname !== step.route) nav(step.route); }, [open, i]); // eslint-disable-line

  const measure = useCallback(() => {
    const el = document.querySelector(`[data-tour="${step.target}"]`) as HTMLElement | null;
    if (!el) { setRect(null); return; }
    el.scrollIntoView({ block: "nearest", behavior: "smooth" });
    const r = el.getBoundingClientRect();
    setRect({ top: r.top - 6, left: r.left - 6, width: r.width + 12, height: r.height + 12 });
  }, [step]);

  useLayoutEffect(() => {
    if (!open) return;
    let tries = 0;
    const t = setInterval(() => { measure(); if (++tries > 12) clearInterval(t); }, 120); // wait for route content to render
    window.addEventListener("resize", measure);
    return () => { clearInterval(t); window.removeEventListener("resize", measure); };
  }, [open, i, loc.pathname, measure]);

  useEffect(() => { if (open) nextRef.current?.focus(); }, [open, i]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key === "ArrowRight") setI((x) => Math.min(x + 1, TOUR_STEPS.length - 1));
      if (e.key === "ArrowLeft") setI((x) => Math.max(x - 1, 0));
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;
  const last = i === TOUR_STEPS.length - 1;
  const popW = 340;
  let pos: React.CSSProperties = { top: "50%", left: "50%", transform: "translate(-50%, -50%)" };
  if (rect && rect.height > window.innerHeight * 0.55) {
    pos = { bottom: 20, right: 20 }; // large target: keep the card out of its way
  } else if (rect) {
    const roomRight = window.innerWidth - (rect.left + rect.width);
    if (roomRight > popW + 24) pos = { top: Math.max(16, Math.min(rect.top, window.innerHeight - 240)), left: rect.left + rect.width + 14 };
    else if (rect.top + rect.height + 230 < window.innerHeight) pos = { top: rect.top + rect.height + 12, left: Math.max(16, Math.min(rect.left, window.innerWidth - popW - 16)) };
    else pos = { top: Math.max(16, rect.top - 230), left: Math.max(16, Math.min(rect.left, window.innerWidth - popW - 16)) };
  }
  return (
    <>
      <div className="tour-spot" style={rect ?? { top: "50%", left: "50%", width: 0, height: 0 }} aria-hidden="true" />
      <div className="tour-pop" style={pos} role="dialog" aria-modal="true" aria-labelledby="tour-title" key={i}>
        <h2 id="tour-title">{step.title}</h2>
        <p>{step.body}</p>
        <div className="tour-foot">
          <div className="tour-steps" aria-label={`Step ${i + 1} of ${TOUR_STEPS.length}`}>
            {TOUR_STEPS.map((_, k) => <i key={k} className={k === i ? "on" : ""} />)}
          </div>
          <button className="ghost" onClick={onClose}>Skip</button>
          {i > 0 && <button onClick={() => setI(i - 1)}>Back</button>}
          <button ref={nextRef} className="primary" onClick={() => (last ? onClose() : setI(i + 1))}>{last ? "Done" : "Next"}</button>
        </div>
      </div>
    </>
  );
}
