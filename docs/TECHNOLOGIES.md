# Technology choices

| Technology | What it does here | Why it fits | Tradeoff |
| --- | --- | --- | --- |
| Python 3.12 | Application, adapters, orchestration, tests, documentation generation | One readable language across both projects | CPU-bound work needs processes at higher load |
| Streamlit + Plotly | Interactive topology, source inspector, experiments, trace waterfall | Python-native demo that is easy to run and inspect | Rerun/session model; not a general multiuser frontend |
| FastAPI + Pydantic | HTTP contract, validation, experiment endpoints | Explicit request models and generated API documentation | One-process coordination in this lab |
| SQLAlchemy | Source observations, projections, history, evidence | Transactions and a shared SQLite/PostgreSQL model | Migrations and optimized bulk reconciliation remain future work |
| SQLite | Zero-service local catalog storage | Durable local startup without Docker | Single-writer, unsuitable for horizontal API scaling |
| PostgreSQL 17 | Container/CI catalog storage | Concurrent relational queries and a path to operational deployment | Switching databases alone does not make the catalog distributed |
| OpenTelemetry Python SDK | Correlated traces, logs, counters, histograms | One instrumentation model and W3C propagation | SDK buffers are not durable |
| OTel Collector contrib 0.160.0 | OTLP ingress, memory limiter, batching, persistent export | Tests the actual delivery machinery | Finite queue, local disk, finite retries |
| Prometheus 3.14.0 | Scraping, counter-series comparisons, collector self-metrics | Inspectable PromQL and direct cardinality evidence | Local retention; historical process series must be scoped carefully |
| Loki 3.7.7 | OTLP logs and structured metadata | Query events by service/experiment without indexing every request ID | Local filesystem storage and lab retention management |
| Jaeger 2.20.0 | Distributed trace retrieval and UI | Native macOS/Linux binaries and a direct trace API | Lab uses ephemeral memory storage |
| pytest + Streamlit AppTest | Domain, API, relay, and UI behavior | Automated failure-path and interaction checks | AppTest does not replace visual browser inspection |
| GitHub Actions | Linux integration and PostgreSQL checks | Reproducible evidence alongside the source | Depends on runner/package availability |

`requirements.lock` pins the Python environment used for verification. `pyproject.toml` declares compatible dependency ranges. `scripts/install_tools.py` pins official native binaries and verifies their published asset digest before execution. Application code is all Python; the standard backends are existing third-party tools, not Python reimplementations.

## Useful primary references

- [Streamlit AppTest](https://docs.streamlit.io/develop/api-reference/app-testing) describes the Python UI testing surface.
- [OpenTelemetry Collector resilience](https://opentelemetry.io/docs/collector/resiliency/) explains queue, retry, and persistent storage boundaries.
- [Prometheus data model](https://prometheus.io/docs/concepts/data_model/) explains why every distinct label set creates a series.
- [Loki OTLP ingestion](https://grafana.com/docs/loki/latest/send-data/otel/) covers resource labels and structured metadata.
- [Backstage descriptor format](https://backstage.io/docs/features/software-catalog/descriptor-format/) defines the exported entity shapes.
- [Jaeger architecture](https://www.jaegertracing.io/docs/latest/architecture/) explains its collection and storage components.

There is no LLM dependency or API key. Adding an AI component should solve a measured investigation problem and come with evaluation, citations, access boundaries, and clear abstention behavior.
