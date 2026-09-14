# Operating the lab

## Start, inspect, stop

Run `python scripts/run_stack.py` from the repository with the virtual environment active. The launcher owns its child processes and stops them on Ctrl-C. It reports a failed child and the corresponding `.runtime/logs/<service>.log`. Do not run multiple copies or share the same ports with Compose.

| Surface | Native URL | Purpose |
| --- | --- | --- |
| Streamlit | http://127.0.0.1:8501 | Catalog, experiment runner, field guide |
| FastAPI | http://127.0.0.1:8001/docs | API request/response contracts |
| Prometheus | http://127.0.0.1:9090 | Metrics, targets, PromQL |
| Loki readiness | http://127.0.0.1:3100/ready | Log backend health |
| Jaeger | http://127.0.0.1:16686 | Trace UI |
| Collector health | http://127.0.0.1:13133 | Collector availability |
| Collector self-metrics | http://127.0.0.1:8888/metrics | Accepted data, exporter queues |

The recovery script additionally uses 14318, 18888, 18889, 23133, and 18200. It cleans up its own temporary processes/storage when it finishes.

## A source looks stale or conflicts

Select the entity and inspect “Why this value?” Compare the chosen source to the conflicting evidence. A stale source's value is retained and flagged; it is not silently replaced just because another source is fresher. Decide whether the authoritative source should be corrected before changing policy.

For the fictional demo, apply **Healthy baseline** to refresh all three sources and clear injected scenarios. This action restores the fixture values, so do not use it to maintain manually imported real inventory. The example importer defaults to incremental updates to avoid treating a small fixture as the whole fleet.

## A telemetry experiment is incomplete

1. Check Signal lab backend readiness, then `.runtime/logs/` for errors.
2. Inspect the saved assertions and request errors. A passing HTTP workload alone does not prove export.
3. Check Prometheus targets and Collector queue occupancy. Metric export and log/trace indexing are asynchronous.
4. Inspect the saved trace IDs in Jaeger and log metadata in Loki. The evidence JSON contains the exact observed counts.
5. Retry after the failure is resolved; retain both run records for comparison.

Loki can take about 15–20 seconds to become ready at startup. Jaeger trace data disappears on restart in this lab; experiment JSON remains in SQL and should be interpreted as the evidence captured at run time. Old service-instance metrics can remain in Prometheus; the UI scopes comparisons to current process IDs.

If a run remains `running` after an API crash, it is an interrupted run, not a success. The current version stores the initial record and final result but does not have a durable background job scheduler or automatic cancellation recovery.

## Retention and local storage

Catalog/audit/experiment data and Loki files persist under `.runtime/` in native mode. Prometheus retains two hours. Jaeger holds up to 10,000 traces in memory. The lab does not configure automatic Loki or SQL pruning; monitor disk and stop the lab when finished. Preserve any evidence you need before intentionally clearing your own runtime directory or Docker volumes.

Workload request counts are bounded, but repeated **Label growth** runs accumulate metric series in the SDK and backends. Restart the lab processes to begin with new instance IDs. This is a demonstration of cardinality cost, not a sustained load generator.

## Sharing and deployment

The public repository contains source, invented fixtures, and generated test evidence. It contains no credentials or private infrastructure inventory. To run a shared demo, provide authentication for Streamlit and every exposed API/observability UI, use TLS, isolate the fault relay, set budgets/rate limits, and replace lab storage/retention choices according to the intended audience.

`LAB_API_TOKEN` protects catalog and experiment API access plus relay controls when set. Native scripts inherit environment variables; `.env.example` is a reference and is **not automatically loaded**. Compose reads `.env` using Docker's normal interpolation. Do not commit an actual `.env` file.

`FLEET_API_URL` is the API address used by the Streamlit server. `FLEET_PUBLIC_API_URL` is the browser-facing address for runbook links; it defaults to the local API port so links also work when Streamlit uses the internal Compose hostname.
