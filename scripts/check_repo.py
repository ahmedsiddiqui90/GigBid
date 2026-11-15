"""Repository rules enforced in CI:
  1. no secrets committed (.env, API-key-looking strings)
  2. gigsim/ unchanged (checksum)
  3. every prompt lives in agent/prompts/ (no long prompt-like strings inline in code)
  4. every number in README.md's results tables traces to a file in evals/results/
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
errors: list[str] = []

tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True).stdout.split()

# 1. secrets
if ".env" in tracked:
    errors.append(".env is committed")
key_pat = re.compile(r"(gsk_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9]{20,}|lsv2_[A-Za-z0-9_]{20,}|ghp_[A-Za-z0-9]{20,})")
for f in tracked:
    p = ROOT / f
    if p.suffix in (".py", ".ts", ".tsx", ".md", ".yaml", ".yml", ".json", ".toml", ".example", ".txt") and p.exists():
        if key_pat.search(p.read_text(encoding="utf-8", errors="ignore")):
            errors.append(f"possible secret in {f}")

# 2. gigsim checksum
digest = hashlib.sha256((ROOT / "gigsim" / "app.py").read_bytes().replace(b"\r\n", b"\n")).hexdigest()
if digest != (ROOT / "gigsim" / "CHECKSUM").read_text().strip():
    errors.append("gigsim/app.py changed (checksum mismatch)")

# 3. prompts only in agent/prompts
prompt_like = re.compile(r'"""[^"]*(You are|Return JSON|Rules:)[^"]*"""|"(You are a|You are an) [^"]{40,}"')
for f in tracked:
    if f.endswith(".py") and not f.startswith(("agent/prompts/", "tests/", "evals/", "scripts/check_repo")):
        if prompt_like.search((ROOT / f).read_text(encoding="utf-8", errors="ignore")):
            errors.append(f"inline prompt-like text in {f}; move it to agent/prompts/")

# 4. README numbers trace to evals/results
readme = (ROOT / "README.md").read_text(encoding="utf-8") if (ROOT / "README.md").exists() else ""
results_text = " ".join(p.read_text(encoding="utf-8") for p in (ROOT / "evals" / "results").glob("*.json"))
nums_in_results = set(re.findall(r"-?\d+\.\d+", results_text))
section = readme.split("<!-- results:start -->")[1].split("<!-- results:end -->")[0] if "<!-- results:start -->" in readme else ""
for n in re.findall(r"(?<![\w.])-?\d+\.\d+(?![\w.])", section):
    if n not in nums_in_results and n.rstrip("0") not in {x.rstrip("0") for x in nums_in_results}:
        errors.append(f"README results number {n} not found in evals/results/*.json")

if errors:
    print("\n".join(f"FAIL {e}" for e in errors))
    sys.exit(1)
print("repo checks passed")
del json
