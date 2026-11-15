"""X2 extension: A/B test of two proposal strategies on GigSim reply rate, with significance tests.
Uses proposals from evals/results/agent_*.json (each carries its randomly assigned arm and simulated reply)."""
from __future__ import annotations

import json
import math

from scipy.stats import fisher_exact, norm

from evals.runners.common import RESULTS, save


def main() -> None:
    arms: dict[str, list[int]] = {}
    seen = set()
    for p in sorted(RESULTS.glob("agent_*.json")):
        if "inj_off" in p.stem:
            continue  # defences disabled: not a production proposal
        for x in json.loads(p.read_text(encoding="utf-8")).get("proposals_detail", []):
            key = (p.stem, x["job_id"])
            if key in seen or not x.get("strategy"):
                continue
            seen.add(key)
            arms.setdefault(x["strategy"], []).append(int(x["replied"]))
    (a, ya), (b, yb) = sorted(arms.items())[:2]
    n1, n2, s1, s2 = len(ya), len(yb), sum(ya), sum(yb)
    p1, p2 = s1 / n1, s2 / n2
    pp = (s1 + s2) / (n1 + n2)
    se = math.sqrt(pp * (1 - pp) * (1 / n1 + 1 / n2)) or 1e-9
    z = (p1 - p2) / se
    p_z = 2 * (1 - norm.cdf(abs(z)))
    _, p_f = fisher_exact([[s1, n1 - s1], [s2, n2 - s2]])
    # minimum detectable difference at 80% power, alpha 0.05 (normal approximation)
    mde = (1.96 + 0.84) * math.sqrt(pp * (1 - pp) * (1 / n1 + 1 / n2))
    out = {"arms": {a: {"n": n1, "replied": s1, "reply_rate": round(p1, 3)}, b: {"n": n2, "replied": s2, "reply_rate": round(p2, 3)}},
           "difference": round(p1 - p2, 3), "z": round(z, 3), "p_value_z": round(p_z, 4), "p_value_fisher": round(p_f, 4),
           "min_detectable_difference_80pct_power": round(mde, 3), "significant_at_0.05": p_f < 0.05}
    save("ab_test", out)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
