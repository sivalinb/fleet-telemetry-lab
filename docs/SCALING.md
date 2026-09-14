# Scaling

Queue capacity depends on measured exporter requests per second, tolerated outage duration, and headroom. Request counts must be translated into bytes using realistic batch sizes and WAL overhead. Recovery export capacity must exceed ongoing ingestion for a backlog to drain.

Place collectors by host, region, and failure domain; define signal-specific backpressure and retention. Persistent local queues cover accepted backlog through tested process restarts. They do not protect upstream buffers, exhausted retry budgets, rejected ingress, or loss of the underlying disk.

Shared execution requires a durable job queue, worker leases, authenticated cancellation ownership, and cleanup supervision. Add idempotent completion and recovery of orphaned subprocesses before increasing API workers. Use durable trace storage, object-backed logs, highly available metrics, and explicit retention for longer-lived deployments.

Benchmark fixed traffic mixes and payload sizes under normal load, backend stalls, queue saturation, disk pressure, and process crashes. Measure accepted/rejected/duplicate/missing IDs, per-signal bytes, p95 delivery delay, queue occupancy, drain rate, and resource usage. No sustained throughput or fleet-size limit has been established by this bounded lab.
