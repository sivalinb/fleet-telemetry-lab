# Verification

Python tests cover resource contracts, forbidden metric labels, signal counters, relay failure/recovery, API authentication, request limits, run exclusion, cancellation, restart interruption, persisted errors, isolated queue configuration, HTML escaping, evidence export, and Gradio rendering. A separation regression verifies that storage contains only experiment records and catalog routes are absent.

`scripts/verify_reliability.py` runs all nine scenarios against actual Collector, Prometheus, Loki, and Jaeger processes. It verifies cancellation and owned-process cleanup, a streamed Gradio request, contract validation, and HTML/JSON reports. `scripts/verify_recovery.py` separately kills an isolated Collector and checks its accepted backlog after WAL replay.

Prometheus rule fixtures test firing and quiet cases for scrape failure, queue pressure, terminal export failures, and unbounded labels. `scripts/verify_postgres.py` verifies experiment storage and restart persistence in a disposable PostgreSQL database.

GitHub Actions runs Python, native backend integration, and PostgreSQL checks independently. The checked-in Compose configuration is an alternative deployment path; a successful native run is not evidence that the whole Compose stack was executed.

Full evidence is stored locally under `evidence/` and excluded from Git. A passing loss experiment confirms the stated loss hypothesis; it does not assert delivery of every attempted signal. Absence is evaluated within a bounded observation window. Measured durations are run evidence, not delivery commitments.
