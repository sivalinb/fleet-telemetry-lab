# Technologies

| Technology | Responsibility |
| --- | --- |
| Python, FastAPI, Pydantic | Workloads, run lifecycle, request contracts, and orchestration |
| Gradio and Plotly | Pipeline state, queue charts, delivery comparison, and evidence inspection |
| OpenTelemetry Python SDK | Metrics, logs, traces, resource attributes, and propagation |
| OpenTelemetry Collector Contrib | Receiving, batching, queues, retries, and WAL-backed export |
| Prometheus | Metrics queries, Collector visibility, and alert rule evaluation |
| Loki | Log storage and run-scoped evidence queries |
| Jaeger | Trace storage, service chains, and duration evidence |
| SQLAlchemy, SQLite / PostgreSQL | Persisted experiment state and results |
| HTTPX, pytest, GitHub Actions | Backend clients and repeatable verification |

Official backend versions and SHA-256 checks are recorded by `scripts/install_tools.py`. All application and orchestration code is Python. Infrastructure YAML configures the external backend processes.
