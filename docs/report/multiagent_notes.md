**What happened.** The decisive difference was not answer quality but **reliability of model-driven tool use**. The
single ReAct agent and the supervisor failed on 3 of 4 jobs each, almost always with a malformed tool call rejected by
the provider: a hallucinated tool name (`search_e Dining`), invalid parameters, or (supervisor) a context that grew past
the per-request token limit. Our graph completed 4/4 because no model chooses tools in it: nodes call MCP tools in code,
and models only fill typed hand-offs. Where the supervisor did finish (dev-ai_ml-001), it bid correctly but made
**2 unsupported claims** and took 177 s and 13.8k tokens; our graph's draft for the same job had 0 unsupported claims
after verification with about the same tokens.

**Where the single agent wins.** On the scam job (dev-ai_ml-029) the ReAct agent skipped correctly in 3.2 s; for
obvious skips one model call is enough, and our graph spends its fixed overhead (three parallel analyses) before the
rule-based skip. We already short-circuit cheaply (1,777 tokens for that skip), but a router that sends "obvious scam"
posts straight to a skip would make the graph cheaper still.

**Would we ship the single agent?** Not for anything that writes to a marketplace: its failure mode is a silent or
crashing tool call, and nothing in it verifies claims or enforces policy. We would use a single agent as an
interactive helper (answering a freelancer's question about one job), where a failed call is visible and harmless.
