# Two views of the same infrastructure

When inventory, service ownership, and telemetry live in separate systems, a simple question becomes expensive: **What is affected, who owns it, and what evidence should I inspect?** Fleet Atlas makes that question concrete in a small, runnable lab.

## Project 1 — A catalog with reasons behind its answers

The fleet catalog joins a service catalog, Kubernetes observations, and Redfish/BMC observations. A machine is identified by a stable serial-based key such as `node:FTL-A11`. A changed hostname updates an observation; it does not create a second physical machine.

Each field has a selected value, source, and observation time. Ownership prefers the service catalog. Serial, model, accelerator count, and rack placement prefer Redfish. Other fields follow source priority, then observation time, then source ID for deterministic ties. Conflicting owner claims remain visible even when a winner can be selected.

The interactive graph connects clusters, racks, nodes, services, and teams. Selecting a node reveals services that depend on it directly or transitively. This is **dependency exposure**, not a claim that every listed service is down: redundancy, traffic, and health are separate concerns.

Source disappearance is not deletion. A full snapshot can mark an observation absent while another source still reports the entity. Even when all sources withdraw it, the last known record and audit history remain. Freshness is evaluated on reads, so a quiet source becomes stale without needing another import.

## Project 3 — A telemetry reliability lab with receipts

Three instrumented Python services make real HTTP calls: gateway → scheduler → worker. The worker hashes bytes and can add an explicit delay. Each request emits a propagated trace, two structured logs per service, a counter increment, and a duration histogram.

The Collector receives OTLP over HTTP. Prometheus scrapes metrics. A Python fault relay sits between the Collector and Loki/Jaeger so an experiment can return 503 temporarily and let the real exporter retry queues respond.

| Experiment | Question answered | Evidence |
| --- | --- | --- |
| Baseline | Did the request produce usable telemetry? | Complete three-service traces, gateway logs, exported counters |
| Label growth | What happens if request IDs become metric labels? | Three added counter series per request |
| Contract gate | Can we prevent that instrumentation mistake? | Rejected requests, no added service work, no gateway events |
| Slow worker | Can a trace locate the introduced delay? | Worker spans at least 180 ms |
| Backend outage | Does a short export failure lose this workload? | Actual 503 responses, queued batches, drained queue, recovered traces/logs |
| Collector crash | Does queued telemetry survive an abrupt process loss? | A killed/restarted isolated Collector, persistent storage, recovered unique events |

## What is real, and what is modeled?

**Real execution:** Python HTTP calls, SQL persistence, source reconciliation, OTLP encoding/export, PromQL and LogQL queries, trace retrieval, injected exporter failures, and process restart recovery.

**Modeled context:** the fleet, teams, rack locations, GPU counts, and service-to-node placement. All names and sample data are invented. No Apple, Oracle, NVIDIA, or other employer infrastructure data is used.

**Future work:** live cluster polling, incident SaaS integration, an AI evidence assistant, multitenancy, distributed catalog processing, durable production trace storage, GPU workloads, and production capacity validation.

The two projects deliberately share canonical service/node identities. The catalog supplies ownership context; the Signal lab shows the evidence trail for services represented by that catalog. The current workload uses the fixture mapping rather than dynamically scheduling onto physical machines.
