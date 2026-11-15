"""CI gate: fail if a smoke eval regresses past the thresholds in agent/config.yaml (eval_gates)."""
import json
import sys

from agent.settings import config

r = json.loads(open(sys.argv[1], encoding="utf-8").read())
g = config().eval_gates
unsup = r["proposals"]["unsupported_after_per_proposal"]
f1 = r["decision"]["bid"]["f1"]
fails = []
if unsup > g["max_unsupported_claims_per_proposal"]:
    fails.append(f"unsupported claims per proposal {unsup} > {g['max_unsupported_claims_per_proposal']}")
if f1 < g["min_bid_skip_f1"]:
    fails.append(f"bid/skip F1 {f1} < {g['min_bid_skip_f1']}")
print(f"unsupported/proposal={unsup} bid_f1={f1}")
if fails:
    print("GATE FAILED: " + "; ".join(fails))
    sys.exit(1)
print("gate passed")
