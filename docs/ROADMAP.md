# Extension plan

These are planned extensions, not features implemented in the current demo. Each has an acceptance test so it can become a reviewable project increment.

| Order | Extension | Small deliverable | Acceptance evidence |
| --- | --- | --- | --- |
| 1 | Live source collectors | Read-only Kubernetes pagination/watch and vendor-specific Redfish member resolution; polling checkpoints | Reconnect, pagination, RBAC denial, incomplete snapshot protection, fixture replay |
| 2 | Catalog operations | Explicit decommission workflow, field policy configuration, Alembic migrations, scheduled refresh | Migration rollback, audit lineage, no silent identity merge |
| 3 | Service telemetry lookup | Catalog-driven resource mapping and one-click service log/trace queries | Unknown/mismatched service mapping shown; no stale owner hidden |
| 4 | Incident workspace | Draft incident from selected service, snapshot owner and evidence, timeline and post-incident template | Repeat action is idempotent; historical ownership retained; external sends require explicit action |
| 5 | AI evidence assistant | Read-only tools for inventory and telemetry, cited investigation suggestions, no autonomous remediation | Eval set with correct cause, ambiguous cause, missing evidence, stale owner, malicious log content; measure abstention and citation correctness |
| 6 | Real accelerator signals | DCGM exporter + Redfish health ingestion on an explicitly provisioned GPU host | Actual hardware/model/version recorded; compare sensor values to raw source; no synthetic performance claims |
| 7 | Reliability experiments | Queue saturation, disk exhaustion, partial backend failure, trace sampling, retry expiry, load ramp | Expected data loss measured where guarantees end; no broad zero-loss claim |
| 8 | Multiuser service | OIDC, tenant-scoped RBAC, TLS ingress, rate limits, durable job queue, HA database | Isolation checks, concurrent imports, restore drills, controlled rollout |

## An AI extension worth building

Start with a question such as “Which services depend on this node, and what changed around this trace?” Give an assistant narrow, read-only tools that return provenance and freshness along with values. Treat log bodies, imported descriptions, and runbooks as untrusted data. Require source citations in generated answers and an explicit “insufficient evidence” response when the signals disagree.

Create a small evaluation set before selecting an agent framework. Include a known worker delay, owner conflict, missing trace, delayed log, stale source, and an instruction embedded in log text. Score evidence retrieval, correct attribution, unsupported claims, and abstention. Compare the agent against a deterministic catalog/query workflow; keep it only if it improves the measured task.

## Suggested next three increments

First, make one real read-only source integration reliable under reconnect and partial results. Second, add schema migrations and a catalog refresh job with clear operational ownership. Third, connect an incident evidence bundle to the service inspector. These steps strengthen the infrastructure foundation before adding more UI or model dependencies.
