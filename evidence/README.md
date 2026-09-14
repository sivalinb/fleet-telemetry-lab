# Recorded execution evidence

This is a point-in-time record from Python 3.12.14 on Darwin arm64. All inventory is fictional and all telemetry comes from this lab. The JSON files include the measured results and assertions, not estimated outcomes.

- **56 automated tests passed**, including catalog, API, relay, and Streamlit AppTest behavior.
- **Five live scenarios passed** against native OpenTelemetry Collector, Prometheus, Loki, and Jaeger.
- **Abrupt Collector restart passed**: 20/20 traces and 20/20 unique log events recovered after SIGKILL and WAL replay; 12 batches were queued before the crash.
- Docker was not installed on the local verification machine. Compose is provided as an alternative and was not executed locally. The PostgreSQL path has a dedicated GitHub Actions job; inspect the repository Actions run for its current result.

| Scenario | Result | Completed/requested | Complete trace chains | Gateway logs |
| --- | --- | --- | --- | --- |
| baseline | passed | 12/12 | 12 | 24 |
| label-growth | passed | 12/12 | 12 | 24 |
| contract-gate | passed | 0/12 | 0 | 0 |
| slow-worker | passed | 12/12 | 12 | 24 |
| backend-outage | passed | 12/12 | 12 | 24 |

`live-experiments.json` contains trace IDs, logs, before/after metrics, queue samples, measured latency, and the individual assertions. `collector-recovery.json` records the isolated crash/replay proof. `unit-tests.xml` is the pytest JUnit report. `native-tools.json` records version-pinned official release assets and SHA-256 digests. `verification-summary.json` is a compact machine-readable record.

The 36 counter series added by the label-growth run represent 12 requests across three services. Histogram series are additional and are not included in that number. Recovery covers data already persisted in the export queues. It does not establish exactly-once delivery or loss-free behavior beyond the tested failure.

To regenerate: run the commands in [TESTING.md](../docs/TESTING.md). CI publishes new evidence as workflow artifacts. Checked-in files are a sample run, not a live health indicator.
