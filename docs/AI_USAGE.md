# AI usage

| Tool | Used for | Files |
|---|---|---|
| Claude Code (Claude Opus) | planning, scaffolding and most implementation, tests, docs, running evaluations | whole repository |

I reviewed, ran and debugged the generated code; I am accountable for every line.

## Things the assistant got wrong that were caught

1. **Claim detection was too broad.** The first claim splitter treated plan sentences ("I would start with a call...")
   as experience claims, so the verifier deleted them and drafts shrank. Caught in the first end-to-end smoke run;
   fixed by excluding future/plan phrasing (`rag/verify.py`, `FUTURE`).
2. **The LLM verifier was too lenient.** It accepted "anomaly detection models in PyTorch" for a project whose evidence
   never mentions PyTorch. Added a deterministic override: numbers and named technologies must appear in the cited
   evidence (`specific_violation`).
3. **Then the repair was too destructive:** whole sentences were deleted for one wrong technology. Changed to strip
   only the unverifiable terms from partial claims.
4. **Generic words inflated fit.** Real Kaggle jobs without skill tags scored fit 1.0 because "developer" matched the CV.
   Fixed with a generic-word filter and a discount for jobs with fewer than 3 requirements.
5. **Windows event loop.** psycopg async cannot run on uvicorn's default Proactor loop on Windows; added
   `scripts/serve_api.py`.
6. **Playwright route mock** `**/api/**` also intercepted Vite's `/src/lib/api/*.ts` modules, so every test timed out;
   fixed by matching only paths that start with `/api/`.
