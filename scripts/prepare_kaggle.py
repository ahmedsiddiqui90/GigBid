"""Download and preprocess REAL Upwork job postings from Kaggle (public datasets, via kagglehub).

Sources (see docs/DATA_CARD.md for licence and attribution):
  - asaniczka/upwork-job-postings-dataset-2024-50k-records   (title, description, hourly range, budget, country)
  - ahmedmyalo/upwork-freelance-jobs-60k                      (adds Connects, client spend, rating, payment status)

Outputs
  data/gigsim/market_stats.json   pricing statistics per category (used by the Pricing Strategist via MCP)
  data/processed/jobs_real.json   300 cleaned real jobs injected into the GigSim job stream ("synthetic": false)

Run: python -m scripts.prepare_kaggle
"""
from __future__ import annotations

import glob
import json
import os
import re
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATASETS = ["asaniczka/upwork-job-postings-dataset-2024-50k-records", "ahmedmyalo/upwork-freelance-jobs-60k"]

CATEGORY_KEYWORDS = {
    "ai_ml": ["machine learning", "deep learning", " llm", "langchain", "openai", "chatbot", "nlp", "computer vision",
              "pytorch", "tensorflow", "rag", "ai agent", "data scien", "model training", "fine-tun"],
    "web_dev": ["react", "next.js", "nextjs", "node", "django", "laravel", "full stack", "full-stack", "frontend",
                "backend", "web app", "website", "wordpress", "shopify", "typescript", "stripe"],
    "data_analysis": ["power bi", "tableau", "excel", "dashboard", "sql", "data analys", "looker", "dbt",
                      "google analytics", "bigquery", "snowflake", "etl", "data cleaning"],
}
SKILL_VOCAB = sorted({
    "Python", "React", "Next.js", "Node.js", "TypeScript", "Django", "SQL", "Excel", "Power BI", "Tableau",
    "PyTorch", "TensorFlow", "LangChain", "OpenAI", "Docker", "AWS", "PostgreSQL", "Stripe", "Shopify",
    "WordPress", "dbt", "Snowflake", "BigQuery", "Looker", "pandas", "scikit-learn", "FastAPI", "GraphQL",
    "Redis", "Celery", "Flutter", "React Native", "Firebase", "Airflow", "computer vision", "NLP", "RAG",
})
_URL = re.compile(r"https?://\S+|www\.\S+")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")


def _categorise(text: str) -> str:
    t = f" {text.lower()} "
    scores = {c: sum(k in t for k in kws) for c, kws in CATEGORY_KEYWORDS.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "other"


def _skills(text: str) -> list[str]:
    t = text.lower()
    return [s for s in SKILL_VOCAB if re.search(r"(?<![a-z])" + re.escape(s.lower()) + r"(?![a-z])", t)][:6]


def _num(x) -> float | None:
    try:
        v = float(str(x).replace("$", "").replace(",", "").strip())
        return v if np.isfinite(v) else None
    except (ValueError, TypeError):
        return None


def load() -> pd.DataFrame:
    import kagglehub

    frames = []
    for ds in DATASETS:
        path = kagglehub.dataset_download(ds)
        for f in glob.glob(os.path.join(path, "*.csv")):
            df = pd.read_csv(f, low_memory=False)
            if "title" in df.columns:  # asaniczka
                out = pd.DataFrame({
                    "title": df["title"], "description": df["description"],
                    "is_hourly": df["is_hourly"].astype(str).str.lower().eq("true"),
                    "hourly_low": df["hourly_low"].map(_num), "hourly_high": df["hourly_high"].map(_num),
                    "budget": df["budget"].map(_num), "country": df["country"], "connects": None,
                    "client_spent": None, "client_rating": None, "payment_verified": None, "source": ds})
            else:  # ahmedmyalo
                out = pd.DataFrame({
                    "title": df["Job Title"], "description": df["Description"],
                    "is_hourly": df["Payment_type"].astype(str).str.lower().str.contains("hour"),
                    "hourly_low": df["Start_rate"].map(_num), "hourly_high": df["End_rate"].map(_num),
                    "budget": df["Job_Cost"].map(_num), "country": df["Client_Country"],
                    "connects": df["Connects_Num"].map(_num), "client_spent": df["Spent($)"].map(_num),
                    "client_rating": df["Rating"].map(_num),
                    "payment_verified": df["Payment_Situation"].astype(str).str.contains("verified", case=False)
                    & ~df["Payment_Situation"].astype(str).str.contains("unverified", case=False),
                    "source": ds})
            frames.append(out)
    df = pd.concat(frames, ignore_index=True)
    df = df.dropna(subset=["title", "description"])
    df["title"] = df["title"].astype(str).str.strip()
    df["description"] = (df["description"].astype(str).map(lambda s: _EMAIL.sub("<email>", _URL.sub("<link>", s)))
                         .str.slice(0, 1500))
    df = df.drop_duplicates(subset=["title", "description"])
    df["category"] = (df["title"] + " " + df["description"]).map(_categorise)
    return df


def market_stats(df: pd.DataFrame) -> dict:
    stats = {}
    for cat, g in df.groupby("category"):
        hourly = g[g["is_hourly"]]
        fixed = g[(~g["is_hourly"]) & (g["budget"].fillna(0) > 0)]
        mid = ((hourly["hourly_low"] + hourly["hourly_high"]) / 2).dropna()
        mid = mid[(mid > 3) & (mid < 500)]
        b = fixed["budget"].dropna()
        b = b[(b >= 5) & (b < 100000)]
        c = g["connects"].dropna()
        stats[cat] = {
            "n_jobs": int(len(g)),
            "hourly_mid_p25": round(float(mid.quantile(0.25)), 1) if len(mid) else None,
            "hourly_mid_median": round(float(mid.median()), 1) if len(mid) else None,
            "hourly_mid_p75": round(float(mid.quantile(0.75)), 1) if len(mid) else None,
            "fixed_budget_p25": round(float(b.quantile(0.25)), 0) if len(b) else None,
            "fixed_budget_median": round(float(b.median()), 0) if len(b) else None,
            "fixed_budget_p75": round(float(b.quantile(0.75)), 0) if len(b) else None,
            "connects_median": round(float(c.median()), 1) if len(c) else None,
        }
    return {"source": DATASETS, "synthetic": False, "categories": stats}


def sample_jobs(df: pd.DataFrame, n_per_cat: int = 100) -> list[dict]:
    jobs = []
    for cat in ["ai_ml", "web_dev", "data_analysis"]:
        g = df[df["category"] == cat].sample(n=n_per_cat, random_state=42)
        for i, r in enumerate(g.itertuples()):
            budget = r.budget if r.budget and np.isfinite(r.budget) else None
            hi = r.hourly_high if r.hourly_high and np.isfinite(r.hourly_high) else 30
            lo = r.hourly_low if r.hourly_low and np.isfinite(r.hourly_low) else 15
            bmax = budget if (not r.is_hourly and budget) else hi * 20
            bmin = budget * 0.7 if (not r.is_hourly and budget) else lo * 20
            jid = f"real-{cat}-{i:03d}"
            jobs.append({
                "job_id": jid, "title": r.title, "description": r.description,
                "skills": _skills(f"{r.title} {r.description}"), "category": cat,
                "budget": {"type": "hourly" if r.is_hourly else "fixed", "min": round(float(bmin or 0)),
                           "max": round(float(bmax or 0)), "currency": "USD"},
                "duration_days": 30, "client_id": f"cl-{jid}", "screening_questions": [],
                "posted_at": "2026-11-10", "split": "stream", "target_persona": None,
                "source": r.source, "synthetic": False,
            })
    return jobs


def main() -> None:
    df = load()
    stats = market_stats(df)
    out = ROOT / "data" / "gigsim"
    out.mkdir(parents=True, exist_ok=True)
    (out / "market_stats.json").write_text(json.dumps(stats, indent=1), encoding="utf-8")
    proc = ROOT / "data" / "processed"
    proc.mkdir(parents=True, exist_ok=True)
    jobs = sample_jobs(df)
    (proc / "jobs_real.json").write_text(json.dumps(jobs, indent=1), encoding="utf-8")
    print(f"rows={len(df)} categories={df['category'].value_counts().to_dict()} sampled={len(jobs)}")


if __name__ == "__main__":
    main()
