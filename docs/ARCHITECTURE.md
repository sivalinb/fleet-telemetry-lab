# Architecture

![Telemetry paths](assets/telemetry.svg)

## Main path

Gateway, scheduler, and worker are instrumented Python services. HTTP requests produce a three-service trace chain, correlated logs, and metrics. The OpenTelemetry Collector exports metrics for Prometheus and forwards logs and traces through a Python fault relay to Loki and Jaeger. Prometheus also scrapes Collector self-metrics.

## Isolated path

Crash, retry-exhaustion, and queue-saturation experiments launch a separate Collector and relay with temporary ports and storage. Each probe carries one span or log. Omitting the batch processor makes the response expose exporter-queue admission. A recovery canary checks backend availability separately from delivery of originals.

## Control and persistence

FastAPI owns one experiment manager and stores progress, evidence, and terminal state in the `experiments` table. Concurrent submissions receive 409. Restarted API processes mark unfinished records interrupted. Gradio reads saved runs and submits bounded jobs; closing its browser does not cancel an API task.

The telemetry package contains no catalog tables, source adapters, fixture inventory, or catalog routes. The separate catalog is optional external context, not a runtime dependency.

## Storage and deployment

Native execution uses SQLite and pinned local backend binaries. Compose uses PostgreSQL and container backends. Collector queues use local file storage when configured. Jaeger traces are ephemeral; saved JSON remains after backend retention or restart removes queryable traces.

Published ports bind to loopback. An optional shared API token is not user authorization. Shared deployments require authenticated access to Gradio and all APIs, TLS, and isolated fault controls. Multiple API workers require durable job ownership and worker leases before deployment.
