/** Renders proposal text; every [evidence-id] citation shows its evidence on hover or keyboard focus. */
export type Ev = { id: string; title?: string; snippet?: string; type?: string; date?: string | null };
export type Claim = { claim: string; label: string; reason?: string };

export function EvidenceText({ text, evidence, claims }: { text: string; evidence: Record<string, Ev>; claims?: Claim[] }) {
  const parts = text.split(/(\[[a-z]{2,4}-[\w-]+\])/g);
  return (
    <div className="letter" data-testid="evidence-text">
      {parts.map((p, i) => {
        const m = p.match(/^\[([a-z]{2,4}-[\w-]+)\]$/);
        if (!m) return <span key={i}>{p}</span>;
        const e = evidence[m[1]];
        return (
          <span key={i} className="cite" tabIndex={0} aria-label={`evidence ${m[1]}`}>
            {p}
            <span className="pop" role="tooltip">
              {e ? (
                <>
                  <b>{e.title}</b> <span className="chip">{e.type}</span>
                  <br />
                  {e.snippet?.slice(0, 320)}
                </>
              ) : (
                <span className="error">Evidence {m[1]} not found</span>
              )}
            </span>
          </span>
        );
      })}
      {claims && claims.length > 0 && (
        <details style={{ marginTop: 10 }}>
          <summary className="muted">Claim verification ({claims.length} claims checked)</summary>
          <ul>
            {claims.map((c, i) => (
              <li key={i}>
                <span className={`chip ${c.label === "supported" ? "ok" : c.label === "partial" ? "warn" : "bad"}`}>{c.label}</span>{" "}
                {c.claim} <span className="muted">{c.reason}</span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
