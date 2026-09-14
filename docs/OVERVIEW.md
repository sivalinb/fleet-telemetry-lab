# Verify the telemetry delivery boundary

An upstream success response does not establish backend delivery. Signals can remain in SDK buffers, be rejected by a full sending queue, expire after retries, or disappear when an in-memory collector crashes.

This project makes those boundaries measurable. The same fault is exercised with different queue configurations, while original signal identities and recovery canaries distinguish persisted recovery from new traffic succeeding after an outage.

The implementation includes real HTTP and OTLP, bounded failure injection, durable run records, and evidence exports. It makes no GPU benchmark, production deployment, or exactly-once delivery claim.
