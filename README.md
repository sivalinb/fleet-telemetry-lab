# Telemetry Reliability Lab

**Find where telemetry is lost, and verify what survives.**

A Python and Gradio workbench by [Siva Babu](https://github.com/sivalinb). Real HTTP workloads and OTLP probes exercise OpenTelemetry Collector, Prometheus, Loki, and Jaeger under bounded failures. Saved results distinguish upstream acceptance, queue admission, backend delivery, and recovery.

![Telemetry architecture](docs/assets/telemetry.svg)

## Capabilities

- Nine experiments cover baseline delivery, metric cardinality, instrumentation contracts, slow services, backend outages, persistent and in-memory crashes, retry exhaustion, and queue saturation.
- Each run records its hypothesis, configuration, observed counters, trace/log IDs, assertions, and cleanup state.
- Isolated collectors use their own ports and storage. A fresh canary distinguishes backend recovery from recovery of the original signals.
- Gradio provides pipeline status, saved-run comparison, contract validation, and HTML/JSON evidence exports.

The workload is synthetic CPU work. This project does not measure GPU performance or claim production readiness. The independent [Fleet Infrastructure Catalog](https://github.com/sivalinb/fleet-infrastructure-catalog) owns inventory and reconciliation; it is not required to run this lab.

## Installation

Python 3.12 is recommended; Python 3.11+ is supported. Native observability binaries support macOS and Linux on arm64/amd64.

```sh
git clone https://github.com/sivalinb/fleet-telemetry-lab.git
cd fleet-telemetry-lab
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.lock
python -m pip install --no-deps -e .
python scripts/install_tools.py
python scripts/run_stack.py
```

The application listens on `127.0.0.1:7860`; the API reference is at `127.0.0.1:8001/docs`. Ctrl-C stops owned processes. State and logs are under `.runtime/`. Tool downloads use pinned official releases and SHA-256 verification.

`docker compose up --build` provides an alternative with PostgreSQL. Native and Compose use the same published ports and should run separately. Published ports bind to loopback.

## Verification

```sh
python -m pytest
.runtime/bin/promtool test rules observability/alerts.test.yaml
python scripts/verify_reliability.py
python scripts/verify_recovery.py
```

The last two checks require the running stack. CI repeats Python tests, all nine real scenarios, Gradio API checks, crash recovery, and PostgreSQL persistence. [Evidence](evidence/) contains aggregate verification results; [testing](docs/TESTING.md) explains their boundaries.

## Implementation

| Area | Code |
| --- | --- |
| Gradio interface | [ui.py](backend/fleetlab/ui.py) |
| API and run lifecycle | [api.py](backend/fleetlab/api.py), [jobs.py](backend/fleetlab/jobs.py) |
| Workload and instrumentation | [workload.py](backend/fleetlab/workload.py), [contracts.py](backend/fleetlab/contracts.py) |
| Failure orchestration | [telemetry.py](backend/fleetlab/telemetry.py), [isolation.py](backend/fleetlab/isolation.py) |
| Backend configuration | [observability](observability/) |

[Architecture](docs/ARCHITECTURE.md) · [Technical guide](docs/TELEMETRY_LAB.md) · [Technologies](docs/TECHNOLOGIES.md) · [Scaling](docs/SCALING.md) · [Extensions](docs/EXTENSIONS.md) · [HTML overview](docs/keynote.html)
