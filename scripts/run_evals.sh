#!/bin/sh
# Reproduce every number in README/report. Needs GigSim + MCP servers running; LLM runs need GROQ_API_KEY.
set -x
export PYTHONIOENCODING=utf-8 PYTHONUNBUFFERED=1
PY=${PY:-.venv/Scripts/python}
$PY -m evals.runners.rag_eval
MODEL_PROFILE=offline $PY -m evals.runners.agent_eval --name agent_offline_v2 --stride 3 --variant v2_hybrid
MODEL_PROFILE=offline $PY -m evals.runners.agent_eval --name agent_offline_v0 --stride 3 --variant v0_naive
$PY -m evals.runners.agent_eval --name agent_open_v2 --profile open --variant v2_hybrid --kinds fit --per-persona 2
$PY -m evals.runners.agent_eval --name agent_open_inj_on --profile open --variant v2_hybrid --kinds injection --per-persona 1
GIGBID_DISABLE_DEFENCES=1 $PY -m evals.runners.agent_eval --name agent_open_inj_off --profile open --variant v2_hybrid --kinds injection --per-persona 1
$PY -m evals.runners.agent_eval --name agent_open_small_v2 --profile open --all-small --variant v2_hybrid --kinds fit --per-persona 2
$PY -m evals.runners.multiagent_compare --stride 18
$PY -m evals.runners.tool_granularity
$PY -m evals.runners.judge_calibration --prepare
$PY -m scripts.make_results_table
