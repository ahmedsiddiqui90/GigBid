# Data card

GigBid combines **real** public Upwork job postings with **synthetic** data generated for this project.
Every synthetic record carries `"synthetic": true`; real records carry `"synthetic": false` and a `source`.

## Real data (Kaggle)

| Dataset | Used for | Rows used |
|---|---|---|
| [asaniczka/upwork-job-postings-dataset-2024-50k-records](https://www.kaggle.com/datasets/asaniczka/upwork-job-postings-dataset-2024-50k-records) | job titles/descriptions, hourly ranges, fixed budgets | all rows for statistics |
| [ahmedmyalo/upwork-freelance-jobs-60k](https://www.kaggle.com/datasets/ahmedmyalo/upwork-freelance-jobs-60k) | adds Connects required, client spend, rating, payment status | all rows for statistics |

- **Download:** `kagglehub` (public datasets, anonymous), see `scripts/prepare_kaggle.py`. Raw files are not committed.
- **Preprocessing:** merged on a common schema; descriptions truncated to 1,500 chars; URLs and emails replaced by
  `<link>` / `<email>`; exact duplicates (title + description) dropped (112,660 rows remain); jobs categorised by
  keyword rules into `ai_ml`, `web_dev`, `data_analysis`, `other`; skills extracted with a fixed vocabulary.
- **Outputs:** `data/gigsim/market_stats.json` (hourly and fixed-budget quartiles and median Connects per category;
  used by the Pricing Strategist through the `get_market_stats` tool) and 300 sampled jobs (100 per persona category)
  injected into the GigSim job stream.
- **Licence / attribution:** see each dataset's Kaggle page (the licence field is not exposed by the Kaggle API). Data is
  used for non-commercial coursework with attribution to the dataset authors above; no personal data is used
  (client names are not present; emails/links are removed).
- **Limitations:** scraped postings from 2023-2024; categories are keyword-based (noisy); budgets mix currencies rarely
  and contain outliers (filtered to 5-100,000 USD fixed and 3-500 USD/h); no outcomes (who won) are available, so
  outcome learning uses synthetic past proposals.

## Synthetic data (`scripts/generate_synthetic.py`, seed 4016)

| Asset | Content |
|---|---|
| 3 personas (`data/personas/`) | AI/ML engineer, full-stack web developer, data analyst: CV, 12 case studies each, repo READMEs and code excerpts (same project described differently), client reviews, 50 past proposals labelled won / replied / ignored |
| Clients (`data/gigsim/clients.json`) | marketplace history (payment verified, hires, spend, rating) and **hidden** preferences (must-have skills, budget ceiling, dislike of generic openings, reply bar) used only by the simulated client |
| Job stream | per persona: 16 fit jobs (4 vague, written without skill names), 4 fit jobs with planted prompt injections (canary words), 8 off-domain, 6 scams (free work, Telegram/crypto, fees, off-platform pay), 3 below-floor budgets; plus 6 duplicates |
| Dev set (`evals/datasets/dev.jsonl`) | 111 jobs with gold labels: bid/skip, scam, injection canary, gold evidence item ids, fair price band |
| Held-out split (`data/hidden/`, git-ignored) | same generator with a different seed; never used for tuning; used once for the final test run |

Design choices that make the corpus hard for naive RAG: one skill per case study is only implied (named in the README
or code, not the case study); the same project appears as case study, README, code and review; past proposals'
outcomes matter more than their wording (generic proposals were mostly ignored).

**Limitations:** synthetic text is templated and much cleaner than real portfolios; gold evidence is defined by
project membership, which favours project-level retrieval; the simulated client is a deterministic scoring function,
not a person, so reply rates measure agreement with that function, not real client behaviour.

## What ships (retrieval decision)

See `evals/results/rag_eval.json` and the README results table. The deployed variant is chosen by Recall@5 and nDCG@10
on the dev set, not by default.
