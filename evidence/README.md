# Recorded execution evidence

This is a point-in-time record from Python 3.12.14 on Darwin arm64. All inventory is fictional and all telemetry comes from this lab. The JSON files include the measured results and assertions, not estimated outcomes.

- **77 automated tests passed**, including catalog, API, relay, and Streamlit AppTest behavior.
- **Nine live scenarios passed** against native OpenTelemetry Collector, Prometheus, Loki, and Jaeger. `reliability-suite.json` summarizes them; `reliability/` contains full per-run evidence.
- **Gradio verification passed**: contract validation, a streamed eight-request baseline, both report downloads, and cancellation of an active isolated run with all owned processes exited.
- **Four Prometheus alert rules passed** firing and quiet-case tests.
- **Abrupt Collector restart passed**: 20/20 traces and 20/20 unique log events recovered after SIGKILL and WAL replay; 12 batches were queued before the crash.
- **Earlier v1 Linux and PostgreSQL CI passed** in [run 34803970266](https://github.com/sivalinb/fleet-telemetry-lab/actions/runs/34803970266) for commit `835cfc6`: automated tests, official tool installation, all five live experiments, abrupt Collector recovery, and PostgreSQL reconciliation/restart persistence.
- Docker was not installed on the local verification machine. Compose YAML, mount paths, and loopback bindings were checked; the full Compose stack was not executed locally. CI ran PostgreSQL in a container and the other backends as native Linux processes.

The following table is the earlier five-scenario sample in `live-experiments.json`. The newer reliability suite adds four isolated failure-boundary cases.

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

## Isolated reliability sample

| Scenario | Original traces | Original unique logs | Interpretation |
| --- | --- | --- | --- |
| Persistent crash | 12/12 | 12/12 | Accepted backlog recovered |
| In-memory crash | 0/12 | 0/12 | Expected loss; recovery canary arrived |
| Retry exhaustion | 0/12 | 0/12 | Retry budget expired; recovery canary arrived |
| Queue saturation | 4/12 | 4/12 | Four per signal accepted and recovered; excess inputs rejected |

All four passed their stated hypotheses. This is measured loss/rejection, not a general zero-loss guarantee.
