# Operational reference

Pipeline status separates unavailable measurements from zero values. Queue counters and alerts refer to the main Collector; isolated runs preserve their own counters in evidence. Queue saturation can reject ingress before it reaches durable storage. Retry exhaustion can discard previously accepted signals.

A failed run retains its configuration, phase, assertion failures, and available backend measurements. Process logs are under `.runtime/logs`; owned PIDs are recorded by the launcher. Graceful cancellation stops owned isolated subprocesses. A hard-killed API needs an external supervisor to handle any orphaned processes.

Jaeger is ephemeral in this configuration. Saved trace IDs may outlive their queryable backend records. Exported JSON and HTML retain observed evidence. Repeated label-growth runs accumulate metric series and are bounded experiments rather than a sustained traffic generator.
