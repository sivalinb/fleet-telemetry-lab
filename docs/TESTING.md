# Test cases and verification

The lab separates deterministic correctness checks from live delivery experiments. Assertions test behavior rather than screenshots or static implementation details.

| Area | Trigger | Expected result |
| --- | --- | --- |
| Stable identity | Same serial, changed hostname | One physical node; new name with provenance |
| Replay | Repeat identical source batch | Idempotent success; no duplicate history |
| Conflicting replay | Reuse a batch ID with changed content | Conflict; existing projection remains |
| Event order | Import older source snapshot | Reject stale update |
| Atomicity | Batch contains incompatible kinds/duplicates | Roll back whole batch |
| Ownership | Two sources disagree | Authoritative owner retained; conflict shown |
| Freshness | Source ages past its TTL | Staleness appears on the next read |
| Disappearance | Full snapshot omits one node | Observation withdrawn; node retained and flagged |
| Relationships | Missing reference or cyclic dependencies | Quality issue or bounded cycle-safe traversal |
| Backstage export | Export complete catalog | Resolvable owner/dependency references |
| API boundary | Invalid batch, oversized body, wrong token | Validation/size/authentication error |
| Source parsers | Native Redfish or K8s JSON | Stable canonical identifiers and normalized fields |
| Fault relay | Outage or upstream network failure | Retryable 503, bounded fault duration |
| Streamlit | Change scenario / select field guide | Real API-backed state change; no UI exception |
| Offline UI | Catalog API unavailable | Visible actionable error |

## Gradio reliability suite

Run `python scripts/verify_reliability.py` with the full stack. It verifies all nine scenarios, an active cancellation with owned subprocess cleanup, Gradio contract acceptance/rejection, a streamed baseline, and HTML/JSON downloads. The detailed boundaries and expected-loss assertions are in [TELEMETRY_LAB.md](TELEMETRY_LAB.md).

`backend/tests/test_reliability.py` adds job exclusion, cancellation, restart interruption, exception persistence, missing binaries, isolated configuration, nonfinite metrics, escaped reports, and Gradio evidence rendering. `observability/alerts.test.yaml` checks firing and quiet cases for all four Prometheus rules.

## Workload experiment assertions

Run `python scripts/verify_stack.py` against the full native stack. It executes five sequential runs with 12 requests each and writes `evidence/live-experiments.json`.

- **Baseline:** 12 completed requests, 12 complete gateway/scheduler/worker trace chains, at least 24 gateway logs, 36 service counter increments, and bounded series independent of request count.
- **Label growth:** the same delivery checks plus exactly 36 new counter series (12 requests × 3 services).
- **Contract gate:** 12 rejections before service work, no counter increase, and no gateway logs for that experiment.
- **Slow worker:** complete delivery and every worker span containing at least the introduced 180 ms.
- **Backend outage:** the relay actually rejects exports; the queue is observed nonempty, then drains; complete traces and expected logs are retrieved afterward.

Metric scraping and backend indexing are asynchronous. The runner polls with deadlines rather than treating a transient empty response as a success. Unavailable values stay `null`. Latency values are observations from a laptop/runner and are not GPU or platform performance claims. A run executed alongside unrelated traffic may fail strict counter assertions; the intended lab is single-user with one experiment at a time.

## Abrupt Collector restart

`python scripts/verify_recovery.py` owns a second Collector and relay on separate loopback ports. It blocks exports, sends 20 unique traces and 20 log events, waits for an exporter backlog, kills its Collector abruptly, restarts it with the same `file_storage` directory, restores export, and queries Jaeger/Loki for every unique event. The original demo Collector stays running.

The evidence file records backlog depth, WAL bytes, recovered counts, trace IDs, and each assertion. Recovery of these events does not prove delivery for data still buffered upstream of the persistent queue, nor does it establish exactly-once behavior.

## Reproduce all checks

```sh
python -m pytest --junitxml=evidence/unit-tests.xml
# With the native stack already running:
python scripts/verify_reliability.py
.runtime/bin/promtool test rules observability/alerts.test.yaml
python scripts/verify_recovery.py
# In a clean environment, starts/stops its own full stack:
python scripts/ci_integration.py
```

`scripts/verify_postgres.py` requires an explicit `DATABASE_URL` pointing to a disposable PostgreSQL database. It checks seeded inventory, conflict reconciliation, graph queries, and persistence after the application restarts. GitHub Actions supplies that database in a dedicated job.

See [the evidence directory](../evidence/README.md) for the checked-in execution record and the distinction between local verification and CI verification. CI artifacts are new measurements; checked-in evidence is a point-in-time sample, not a live status badge.
