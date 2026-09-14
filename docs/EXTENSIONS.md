# Extension opportunities

| Capability | Acceptance evidence |
| --- | --- |
| Disk exhaustion and SDK shutdown faults | Separate accepted, rejected, duplicate, and missing signal counts |
| Sustained load | Reproducible rates, payload sizes, resource usage, and delivery distributions |
| Multiple collectors | Failure-domain isolation and bounded recovery under collector loss |
| Durable execution workers | Job ownership, cancellation authorization, and orphan cleanup |
| Durable signal backends | Retention and restore checks across process and storage failures |
| Optional catalog context | Owner/dependency lookup through the separate catalog API, including stale or unavailable results |
| Read-only investigation assistance | Cited evidence, abstention, and hostile log-text evaluations |

These are design directions, not implemented capabilities or delivery commitments.
