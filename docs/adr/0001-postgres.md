# ADR 0001: Postgres for everything stateful

**Decision:** one Postgres holds app tables, the LangGraph checkpointer, the LangGraph store (memory) and the audit log.
**Why:** durability across crashes (C6) and one backup/restore story; fewer services to deploy on a free host.
**Trade-off:** vectors are not in Postgres (see 0002).
