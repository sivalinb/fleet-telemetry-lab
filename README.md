# Fleet Atlas

**Know what you operate. Follow the signal when it breaks.**

A Python infrastructure portfolio project by [Siva Babu](https://github.com/sivalinb). It brings two working systems into one Streamlit demo:

1. **Fleet catalog** — reconcile infrastructure identity, ownership, and dependencies across multiple sources. Inspect provenance, stale observations, conflicting owners, and lifecycle history.
2. **Signal lab** — send real HTTP requests through three Python services, then measure telemetry delivery, cardinality growth, a slow worker, an exporter outage, and Collector crash recovery.

![Fleet Atlas architecture](docs/assets/architecture.svg)

The inventory is fictional: 2 clusters, 4 racks, 12 nodes, 6 services, and 3 teams. The 96 GPU slots are modeled inventory. **Telemetry experiments run actual Python CPU work and real OpenTelemetry, Prometheus, Loki, and Jaeger processes. They do not demonstrate GPU performance or production deployment.**

## Start the Python demo

Requirements: Python 3.12 recommended (3.11+ supported), macOS or Linux on arm64/amd64, internet for the first dependency/tool download, and roughly 2 GB of free disk for binaries and lab data. Windows users can use WSL2 or the Compose option.

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

Open **http://127.0.0.1:8501**. Give the backends about 20 seconds to become ready. Ctrl-C stops the processes created by the launcher. The native path needs no Docker and keeps data in `.runtime/`. Official tool downloads are version pinned and checked against their published SHA-256 digests.

For a smaller demo, `python scripts/run_stack.py --catalog-only` runs the catalog and Streamlit. The Signal lab explicitly shows that telemetry backends are unavailable.

Optional container path: `docker compose up --build`. It uses PostgreSQL for the catalog and mounts named data volumes. See [runtime differences](docs/ARCHITECTURE.md#runtime-paths). Do not run native and Compose simultaneously on the same ports. The checked-in configuration is a local lab; all published ports bind to loopback.

## A five-minute walkthrough

1. Inspect **alpine-11** in Fleet catalog. Follow its recorded dependencies to the worker, gateway, scheduler, and embedding service. Check the owner and field-level provenance.
2. Apply **Ownership conflict**. The service catalog retains authority while the conflicting Kubernetes claim stays visible. Try **Source goes quiet** and **Source drops a node**; neither silently deletes inventory.
3. Open Signal lab and run **Baseline**. Inspect the three-service trace and its correlated gateway logs.
4. Run **Label growth**, then **Contract gate**. The first creates three new counter series per request; the second blocks the forbidden label before work is emitted.
5. Run **Slow worker** and **Backend outage**. Inspect the worker span, the queue samples, and the recorded assertions. Read **Field guide** for the design and limitations.

## Verify it

```sh
python -m pytest
python scripts/verify_stack.py
python scripts/verify_recovery.py
```

The last two commands require the full stack. Crash recovery starts and kills its **own isolated Collector**, reuses that Collector's persistent queue, and verifies unique events in the running backends. It does not kill the main demo Collector. [Test cases and recorded results](docs/TESTING.md) explain exactly what was exercised. JSON evidence is in [evidence/](evidence/); rerunning checks replaces the relevant files.

## Explore the implementation

| Area | Entry point |
| --- | --- |
| Streamlit application | [streamlit_app.py](streamlit_app.py) |
| API / interactive API docs | [backend/fleetlab/api.py](backend/fleetlab/api.py) / http://127.0.0.1:8001/docs |
| Identity and reconciliation | [catalog.py](backend/fleetlab/catalog.py) |
| Read-only source import | [import_source.py](scripts/import_source.py) / [examples](fixtures/README.md) |
| Instrumentation and contract | [workload.py](backend/fleetlab/workload.py), [contracts.py](backend/fleetlab/contracts.py) |
| Live experiment runner | [telemetry.py](backend/fleetlab/telemetry.py) |
| Persistent queue / export configuration | [observability/](observability/) |
| Illustrated field guide | [docs/](docs/OVERVIEW.md) / [portable HTML](docs/field-guide.html) |

All application, importer, orchestration, test, and guide-generation code is Python. Streamlit and Plotly render the interface; standard configuration files describe the third-party observability services. No custom JavaScript application is required.

## Documentation

[What it solves](docs/OVERVIEW.md) · [Architecture](docs/ARCHITECTURE.md) · [Technologies](docs/TECHNOLOGIES.md) · [Test cases](docs/TESTING.md) · [Scaling](docs/SCALING.md) · [Extension plan](docs/ROADMAP.md) · [Runbooks](docs/RUNBOOKS.md)

This is an inspectable lab, with explicit limits: one API worker, a full catalog projection on each import, local authentication only, bounded experiments, local log storage, and ephemeral Jaeger trace storage. It does not include a live GPU cluster, a full CMDB product, an ML model, or an AI agent. The roadmap describes concrete extensions without presenting them as implemented.
