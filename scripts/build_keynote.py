"""Build a portable HTML keynote from checked-in measurements, using Python only.

HTML anchors, details, and radio inputs provide presentation navigation and the
recorded demo. No JavaScript, framework, network fetch, or runtime is required.
"""

import argparse
import base64
from html import escape
import json
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
REPO = "https://github.com/sivalinb/fleet-telemetry-lab"
EVIDENCE_COMMIT = "586fd11f6bcbd670514e0694a4a826523efabee1"
CI = REPO + "/actions/runs/34850570931"


def read_run(name):
    path = ROOT / "evidence/reliability" / (name + ".json")
    run = json.loads(path.read_text())
    if (
        run.get("name") != name
        or run.get("state") != "passed"
        or not run.get("assertions")
        or not all(run["assertions"].values())
    ):
        raise ValueError(f"Cannot present {name} as verified: inspect its evidence")
    return run


def evidence_link(name, label="Recorded evidence"):
    return f'<a href="{REPO}/blob/{EVIDENCE_COMMIT}/evidence/reliability/{escape(name)}.json" target="_blank" rel="noopener">{escape(label)}</a>'


def download(run):
    data = base64.b64encode(json.dumps(run, indent=2).encode()).decode()
    return f'<a class="download" href="data:application/json;base64,{data}" download="{escape(run["name"])}-evidence.json">Download this run’s evidence</a>'


def queue_chart(run, stage):
    """Render measured queue data as an editable SVG chart, never synthetic points."""
    samples = run["samples"]
    if stage == "backlog":
        index = next(
            i for i, s in enumerate(samples) if s.get("phase") == "Backlog established"
        )
        shown = samples[: index + 1]
    elif stage == "restart":
        index = next(
            i
            for i, s in enumerate(samples)
            if s.get("phase") == "Restoring backend exports"
        )
        shown = samples[: index + 1]
    else:
        shown = samples
    end = max(s["elapsed_s"] for s in samples)
    peak = max(s["collector"]["queued_batches"] for s in samples)
    x = lambda value: 52 + value / max(end, 0.01) * 570
    y = lambda value: 205 - value / max(peak, 1) * 150
    points = " ".join(
        f"{x(s['elapsed_s']):.2f},{y(s['collector']['queued_batches']):.2f}"
        for s in shown
    )
    color = "#007b80" if run["name"] == "durable-crash" else "#b65227"
    grid = "".join(
        f'<line x1="52" x2="622" y1="{y(v)}" y2="{y(v)}" stroke="#d9e2e8"/><text x="38" y="{y(v) + 5}" text-anchor="end" fill="#526a7c" font-size="14">{v:g}</text>'
        for v in [0, peak / 2, peak]
    )
    ticks = "".join(
        f'<text x="{x(v)}" y="230" text-anchor="middle" fill="#526a7c" font-size="13">{v:.1f}s</text>'
        for v in [0, end / 2, end]
    )
    last = shown[-1]
    title = (
        f"{run['name']}: observed exporter queue through {last['elapsed_s']} seconds"
    )
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 650 250" role="img" aria-label="{escape(title)}" font-family="Arial,sans-serif"><title>{escape(title)}</title><text x="52" y="24" fill="#526a7c" font-size="15">Queued requests across logs and traces</text>{grid}{ticks}<polyline points="{points}" stroke="{color}" stroke-width="3.5" stroke-linejoin="round" fill="none"/><circle cx="{x(last["elapsed_s"])}" cy="{y(last["collector"]["queued_batches"])}" r="5" fill="{color}"/></svg>'


def replay_mode(run, mode):
    original_count = run["delivery"]["traces_sent"] + run["delivery"]["logs_sent"]
    received = (
        run["delivery"]["traces_received"] + run["delivery"]["unique_logs_received"]
    )
    backlog = run["before_crash_or_recovery"]["queued_batches"]
    restarted = next(
        s for s in run["samples"] if s.get("phase") == "Restoring backend exports"
    )["collector"]["queued_batches"]
    stages = [
        (
            "backlog",
            "Exports are blocked",
            f"{backlog:g}",
            "requests in the exporter queues",
            f"{run['ingress']['accepted_traces']} traces and {run['ingress']['accepted_logs']} logs accepted. The relay is returning 503.",
        ),
        (
            "restart",
            "The collector restarts after SIGKILL",
            f"{restarted:g}",
            "queued requests at the next observed sample",
            "The same queue directory survives the restart."
            if mode == "durable"
            else "The in-memory backlog disappears with the process.",
        ),
        (
            "verify",
            "Backend queries verify the result",
            f"{received}<small> / {original_count}</small>",
            "original signals found after recovery",
            "A fresh trace and log canary also arrived. Original counts exclude the canary.",
        ),
    ]
    radios = "".join(
        f'<input class="phase-input" type="radio" name="{mode}-phase" id="{mode}-{key}" value="{key}" {"checked" if i == 0 else ""}>'
        for i, (key, *_) in enumerate(stages)
    )
    controls = "".join(
        f'<label for="{mode}-{key}" data-for="{key}">{i + 1}. {label}</label>'
        for i, (key, label) in enumerate(
            [
                ("backlog", "Backlog"),
                ("restart", "Restart"),
                ("verify", "Verify delivery"),
            ]
        )
    )
    panels = "".join(
        f'<div class="phase {key}"><figure>{queue_chart(run, key)}<figcaption class="caption">Measured samples. Lines connect observations. The later canary can briefly add two queue requests.</figcaption></figure><div><h3>{title}</h3><div class="big {"loss" if mode == "volatile" and key != "backlog" else "accent"}">{value}</div><p class="sub">{label}</p><p class="caption">{detail}</p></div></div>'
        for key, title, value, label, detail in stages
    )
    return f'<div class="mode-view {mode}">{radios}<div class="phase-controls" role="group" aria-label="{mode.title()} replay stage">{controls}</div><div class="phase-panels">{panels}</div><p class="proof-tag">Saved run {run["id"]} / {run["duration_s"]} seconds total</p>{download(run)}</div>'


def build_keynote(demo_url="http://127.0.0.1:7860/"):
    if (
        urlparse(demo_url).scheme not in {"http", "https"}
        or not urlparse(demo_url).netloc
    ):
        raise ValueError("Demo URL must be an absolute HTTP(S) address")
    demo = escape(demo_url, quote=True)
    runs = {
        name: read_run(name)
        for name in [
            "durable-crash",
            "volatile-crash",
            "retry-exhaustion",
            "queue-saturation",
            "label-growth",
            "contract-gate",
        ]
    }
    summary = json.loads((ROOT / "evidence/verification-summary.json").read_text())
    if (
        summary["unit_failures"]
        or summary["unit_errors"]
        or any(v != "passed" for v in summary["live_scenarios"].values())
    ):
        raise ValueError("Verification summary contains nonpassing results")
    durable, volatile = runs["durable-crash"], runs["volatile-crash"]
    slides = []

    def add(title, body, notes, *, style="", kicker="", sources=""):
        slides.append(
            dict(
                title=title,
                body=body,
                notes=notes,
                style=style,
                kicker=kicker,
                sources=sources,
            )
        )

    add(
        "Telemetry Reliability Lab",
        '<h1>Telemetry<br>Reliability <span class="serif accent">Lab</span></h1><p class="lead">A runnable test of what survives<br>a telemetry pipeline failure.</p><p class="byline">Siva Babu<br>Python + Gradio</p><p class="keyboard-help">12-slide keynote. Next / Back navigate. Notes opens the talk track.<br>The recorded demo works offline. The live demo needs the local stack.</p>',
        "I built this to make telemetry reliability easier to reason about. The lab produces real signals, introduces a controlled fault, and checks what the backends actually received. The demo is a small CPU workload with fictional fleet context. I am presenting a working engineering project, without claiming production GPU performance.",
        style="dark",
        kicker="An infrastructure engineering project",
    )

    add(
        "Where telemetry can disappear",
        '<h2>An accepted signal<br>can still disappear</h2><div class="split"><div><div class="big accent">200 <small>OK</small></div><p class="number-label">A receiver accepted the request.<br>Delivery still depends on what follows.</p></div><ul class="line-list"><li><strong>Before durable storage</strong><p>SDK and batch buffers can disappear with a process.</p></li><li><strong>While exports fail</strong><p>A full queue can reject new data. A retry budget can expire.</p></li><li><strong>During an investigation</strong><p>Missing evidence makes it harder to distinguish a service problem from a telemetry problem.</p></li></ul></div>',
        "Start with the observation that a successful ingress response is only one boundary. In the main pipeline, the collector also batches before enqueueing. In the isolated demo I remove batching so queue admission is easier to observe. These are different guarantees, and that distinction is central to the project.",
        kicker="The problem",
        sources=f'<a href="{REPO}/blob/{EVIDENCE_COMMIT}/docs/TELEMETRY_LAB.md">Implementation and failure boundaries</a>',
    )

    add(
        "A repeatable investigation",
        '<h2>A repeatable investigation</h2><div class="split wide-left"><ol class="plain-steps"><li><div><strong>Choose a hypothesis</strong><p>State what should survive and what loss is expected.</p></div></li><li><div><strong>Apply a bounded fault</strong><p>Real HTTP requests, OTLP, and collector processes.</p></div></li><li><div><strong>Query the backends</strong><p>Compare trace and event IDs with the original inputs.</p></div></li><li><div><strong>Keep the evidence</strong><p>Save assertions, queue samples, and a portable report.</p></div></li></ol><div><p class="quote">“What arrived,<br>and what<br>did we lose?”</p><p class="sub">The same question guides each experiment.</p></div></div>',
        "The UI gives someone a starting hypothesis and a repeatable way to check it. I wanted the investigation to finish with inspectable data. A passing workload request alone does not make an experiment pass. Expected-loss experiments also need evidence that the backend recovered.",
        kicker="The product",
    )

    add(
        "Two paths, shared backends",
        '<h2>Two paths, shared backends</h2><div class="control-line"><strong>Gradio</strong> presents the run. <strong>FastAPI</strong> coordinates it. <strong>SQL</strong> retains its evidence.</div><div class="flow" role="img" aria-label="Main pipeline: Python services through Collector to Prometheus, Loki, and Jaeger. Isolated pipeline: Python probes through an owned Collector and relay to Loki and Jaeger."><p class="flow-label">Workload and instrumentation</p><div class="flow-row"><div class="flow-node"><strong>Python services</strong><span>Gateway, scheduler, worker<br>Correlated HTTP + OTLP</span></div><div class="flow-arrow" aria-hidden="true">→</div><div class="flow-node"><strong>Main Collector</strong><span>Batching and persistent queues<br>Python relay injects export faults</span></div><div class="flow-arrow" aria-hidden="true">→</div><div class="flow-node"><strong>Signal backends</strong><span>Prometheus metrics<br>Loki logs and Jaeger traces</span></div></div><p class="flow-label">Queue and process failures</p><div class="flow-row"><div class="flow-node"><strong>Python probes</strong><span>One trace and log per input<br>Unique IDs for verification</span></div><div class="flow-arrow" aria-hidden="true">→</div><div class="flow-node"><strong>Isolated Collector</strong><span>Own ports, storage, and relay<br>Direct OTLP without batching</span></div><div class="flow-arrow" aria-hidden="true">→</div><div class="flow-node"><strong>Same Loki + Jaeger</strong><span>Original delivery checks<br>Fresh canary after recovery</span></div></div></div><p class="caption">The isolated experiments keep the main collector running. Standard observability backends provide the storage and export machinery.</p>',
        "There are two paths because they answer different questions. The three-service path exercises instrumentation and diagnosis. The isolated path exposes the queue boundary and lets me kill a collector that belongs only to that run. All custom application and orchestration code is Python. The backend products are standard third-party tools.",
        kicker="Architecture",
        sources=f'<a href="{REPO}/blob/{EVIDENCE_COMMIT}/docs/ARCHITECTURE.md">Full architecture and runtime tradeoffs</a>',
    )

    replay = f'<div class="demo-title"><h2>What survives a collector crash?</h2><a href="{demo}" target="_blank" rel="noopener">Open live Gradio demo ↗</a></div><p class="replay-disclosure">Recorded replay. Select storage, then step through the observations. These controls do not run a new experiment.</p><div class="replay"><input class="mode-input" type="radio" id="storage-durable" name="storage" checked><input class="mode-input" type="radio" id="storage-volatile" name="storage"><div class="mode-controls" role="group" aria-label="Queue storage"><label for="storage-durable">Persistent queue</label><label for="storage-volatile">In-memory queue</label></div><div class="mode-views">{replay_mode(durable, "durable")}{replay_mode(volatile, "volatile")}</div></div>'
    add(
        "Recorded crash demo",
        replay,
        "Use the persistent queue first. Click Backlog, Restart, and Verify delivery. Both signal types enter the queue before the crash. The persistent run recovers all originals. Now select In-memory queue and repeat the steps. The same count enters, but originals do not return. The new canary arrives in both runs, so the missing originals are not simply a broken backend query. The lines connect observed samples; they do not claim exact timing between samples. This slide works without a server. Open Gradio only if the local stack is ready.",
        kicker="Interactive demo",
        sources=evidence_link("durable-crash", "Persistent run")
        + " / "
        + evidence_link("volatile-crash", "In-memory run"),
    )

    table_rows = []
    for name, label, meaning in [
        ("durable-crash", "Persistent crash", "Accepted backlog recovers"),
        ("volatile-crash", "In-memory crash", "Originals disappear"),
        ("retry-exhaustion", "Retry exhaustion", "Persistence still has a retry limit"),
        (
            "queue-saturation",
            "Queue saturation",
            "Accepted inputs recover, excess inputs are rejected",
        ),
    ]:
        r = runs[name]
        d = r["delivery"]
        table_rows.append(
            f'<tr><td>{label}</td><td class="num {"loss" if d["traces_received"] < d["traces_sent"] else ""}">{d["traces_received"]}/{d["traces_sent"]}</td><td class="num {"loss" if d["unique_logs_received"] < d["logs_sent"] else ""}">{d["unique_logs_received"]}/{d["logs_sent"]}</td><td>{meaning}</td></tr>'
        )
    add(
        "The observed loss boundary",
        "<h2>The observed loss boundary</h2><table><thead><tr><th>Experiment</th><th>Original traces</th><th>Original logs</th><th>What the run showed</th></tr></thead><tbody>"
        + "".join(table_rows)
        + '</tbody></table><p class="callout">All four hypotheses passed.<br>Three intentionally demonstrate loss or rejection.</p><p class="caption">Each run sent 12 original traces and 12 original logs. Unique log counts exclude the recovery canary. These are bounded lab observations.</p>',
        "Keep the denominator visible. The full-queue experiment accepted four per signal and rejected eight. Those four accepted inputs recovered. A green result there confirms the hypothesis, not delivery of all twelve attempted inputs. The retry case matters because adding disk persistence alone does not remove the configured retry limit. These values are a checked-in sample, not universal performance numbers.",
        kicker="Measured outcomes",
        sources=" / ".join(
            evidence_link(name, label)
            for name, label in [
                ("durable-crash", "Persistent"),
                ("volatile-crash", "Memory"),
                ("retry-exhaustion", "Retries"),
                ("queue-saturation", "Saturation"),
            ]
        ),
    )

    growth = runs["label-growth"]
    gate = runs["contract-gate"]
    add(
        "The cost of a request ID label",
        f'<h2>The cost of a request ID label</h2><div class="split"><div><div class="big accent">+{growth["series_added"]:g}</div><p class="number-label">new counter series<br>from {growth["requested"]} requests across three services</p><p class="caption">Histogram series are additional.</p></div><div><pre>metric attributes\n  profile: <span class="str">"unbounded"</span>\n  <span class="bad">request_id: "unique-per-request"</span></pre><p>The contract gate blocked all <strong>{gate["blocked"]} requests</strong> before service work.</p><p class="sub">Request IDs remain useful in logs and traces.</p></div></div>',
        "This is another way the project supports operational work. A small instrumentation choice creates measurable series growth. The intentionally unguarded scenario produces the bad label. The contract scenario then uses the same validation function that the workload gate uses. I am counting only the request counter family here, not claiming that the total telemetry cost is 36 series.",
        kicker="Common instrumentation",
        sources=evidence_link("label-growth", "Series-growth run")
        + " / "
        + evidence_link("contract-gate", "Contract-gate run"),
    )

    add(
        "One workbench, nine experiments",
        '<h2>One workbench, nine experiments</h2><div class="split"><div><h3>Instrumentation and diagnosis</h3><table class="compact"><tbody><tr><td>Baseline</td><td>Complete signal delivery</td></tr><tr><td>Label growth</td><td>Counter cardinality cost</td></tr><tr><td>Contract gate</td><td>Rejected instrumentation</td></tr><tr><td>Slow worker</td><td>Delay in the right span</td></tr><tr><td>Backend outage</td><td>Queue and recovery evidence</td></tr></tbody></table></div><div><h3>Delivery boundaries</h3><table class="compact"><tbody><tr><td>Persistent crash</td><td>Backlog recovery</td></tr><tr><td>In-memory crash</td><td>Loss after process failure</td></tr><tr><td>Retry exhaustion</td><td>Terminal export failures</td></tr><tr><td>Queue saturation</td><td>Admission and backpressure</td></tr></tbody></table></div></div><p class="caption">The Gradio UI also provides active cancellation, saved-run comparison, contract validation, and HTML/JSON reports. Four Prometheus rules monitor the main pipeline.</p>',
        "The crash comparison is the shortest demo, but it is part of a broader workflow. For an observability audience I would also show the label-growth case. For an SRE audience I would open the slow-worker trace or exporter-outage report. The main-pipeline alert rules do not scrape each temporary isolated collector; those counters are saved in the individual run.",
        kicker="Working scope",
    )

    add(
        "Reproducible evidence",
        f'<h2>Built to inspect and reproduce</h2><div class="metrics"><div class="metric"><div class="big">{summary["unit_tests"]}</div><p class="number-label">automated tests</p></div><div class="metric"><div class="big accent">{len(summary["live_scenarios"])}</div><p class="number-label">real telemetry scenarios</p></div><div class="metric"><div class="big">{summary["alert_rules_verified"]}</div><p class="number-label">alert rules with firing<br>and quiet-case checks</p></div></div><p class="lead">Linux integration and PostgreSQL checks passed in GitHub Actions.</p><p class="caption">Recorded verification for the working lab at commit <code>{EVIDENCE_COMMIT[:7]}</code>. Native macOS and Linux execution. The full Compose stack was not exercised locally.</p>',
        "The counts are from the recorded working lab before this presentation was added. The tests include state and failure behavior: concurrent runs, cancellation, interruption after restart, report escaping, and unavailable metrics. The real integration uses collector and backend processes. PostgreSQL runs in a separate CI job. These checks support reproducibility within the stated lab scope.",
        style="dark",
        kicker="Engineering proof",
        sources=f'<a href="{CI}">Successful CI run</a> / <a href="{REPO}/blob/{EVIDENCE_COMMIT}/evidence/verification-summary.json">Verification summary</a>',
    )

    add(
        "A small team pilot",
        '<h2>A small team pilot</h2><div class="split"><div><p class="quote">One service.<br>One collector change.<br>A known failure.</p><p class="sub">Use the same inputs to compare the old and proposed configurations.</p></div><ol class="plain-steps"><li><div><strong>Agree on the expected outcome</strong><p>What should survive? Where is loss acceptable?</p></div></li><li><div><strong>Run both configurations</strong><p>Keep faults and verification queries comparable.</p></div></li><li><div><strong>Review the evidence together</strong><p>Decide from delivery counts and observed queue behavior.</p></div></li></ol></div>',
        "This is a proposed adoption path, not a claim that a team has deployed it. Start with a bounded collector change in a nonproduction environment. The useful outcome is an explicit delivery expectation and evidence that the new configuration meets it. Faster diagnosis and less repeated manual investigation are goals to measure during a pilot; I have not invented time-saved or ROI numbers.",
        kicker="Where it can help",
    )

    add(
        "Scaling beyond the laptop",
        '<h2>Scaling beyond the laptop</h2><div class="split wide-left"><div><p class="sub">Illustrative queue sizing</p><p class="equation"><span>200 batches/s</span><br>× <span>60 seconds</span><br>× <span>1.5 headroom</span></p><p class="callout">18,000 batches of queue capacity</p><p class="caption">At 500 batches/s export and 200 batches/s new ingress, an 18,000-batch backlog takes about 60 seconds to drain. These are planning assumptions.</p></div><ul class="line-list"><li><strong>Measure bytes and throughput</strong><p>Include WAL overhead, disk reserve, and backend limits.</p></li><li><strong>Give workers durable ownership</strong><p>Job leases, authentication, and cancellation ownership before multiple users.</p></li><li><strong>Expand the failure tests</strong><p>Disk exhaustion, sampling, and upstream buffer loss.</p></li></ul></div>',
        "The calculation is illustrative and is not a benchmark of this laptop. Queue capacity must be considered in bytes as well as exporter requests. Recovery throughput must exceed current ingestion. The present implementation has one API worker and temporary isolated processes, so a shared service needs a durable job supervisor and access controls. Trace storage is intentionally ephemeral in the current lab.",
        kicker="Extension path",
        sources=f'<a href="{REPO}/blob/{EVIDENCE_COMMIT}/docs/TELEMETRY_LAB.md">Capacity assumptions and extension acceptance tests</a>',
    )

    add(
        "Run the comparison",
        f'<h2>Telemetry reliability<br>you can examine</h2><p class="lead">The code is public. The failures are reproducible.<br>The evidence stays with the run.</p><div class="actions"><a class="action" href="{demo}" target="_blank" rel="noopener">Open the live demo ↗</a><a class="action" href="{REPO}" target="_blank" rel="noopener">Inspect the source ↗</a></div><p class="sub"><a href="#s05">Replay the recorded crash comparison</a> or <a href="{REPO}/blob/main/docs/TELEMETRY_LAB.md" target="_blank" rel="noopener">read the field guide</a>.</p><p class="byline">Siva Babu<br><a href="https://github.com/sivalinb">github.com/sivalinb</a></p><p class="caption">Python CPU workloads and real OpenTelemetry backends. The project models fleet context and makes no production GPU performance claim.</p>',
        "Close by offering to run the comparison or inspect an assertion in the code. If the live stack is unavailable, return to the recorded demo. For a live walkthrough, choose the persistent crash with 12 inputs, run it, then repeat with the in-memory queue. Open History and compare the two rows. Download the result so the discussion can continue with evidence.",
        style="dark",
        kicker="Explore the project",
    )

    toc = (
        "<ol>"
        + "".join(
            f'<li><a href="#s{i:02}">{escape(s["title"])}</a></li>'
            for i, s in enumerate(slides, 1)
        )
        + "</ol>"
    )
    pages = []
    for i, slide in enumerate(slides, 1):
        notes = "<p>" + escape(slide["notes"]) + "</p>"
        if slide["sources"]:
            notes += '<p class="source">Sources: ' + slide["sources"] + "</p>"
        previous = (
            f'<a href="#s{i - 1:02}" aria-label="Previous slide">Back</a>'
            if i > 1
            else "<span>Start</span>"
        )
        following = (
            f'<a href="#s{i + 1:02}" aria-label="Next slide">Next</a>'
            if i < len(slides)
            else '<a href="#s01">Restart</a>'
        )
        source = (
            '<p class="caption">' + slide["sources"] + "</p>"
            if slide["sources"]
            else ""
        )
        footer = f'<footer class="footer"><span class="brand">TELEMETRY RELIABILITY LAB</span><details><summary>Notes</summary><div class="notes">{notes}</div></details><details><summary>Slides</summary><div class="contents">{toc}</div></details>{previous}<span class="counter">{i:02} / {len(slides):02}</span>{following}</footer>'
        pages.append(
            f'<section class="slide {slide["style"]}" id="s{i:02}" aria-label="Slide {i}: {escape(slide["title"])}"><p class="kicker">{escape(slide["kicker"])}</p>{slide["body"]}{source}{footer}</section>'
        )
    css = (ROOT / "docs/keynote.css").read_text()
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="description" content="An interactive engineering keynote for the Python and Gradio Telemetry Reliability Lab, with recorded crash-recovery evidence."><title>Telemetry Reliability Lab — Demo Keynote</title><style>'
        + css
        + '</style></head><body><main aria-label="Telemetry Reliability Lab keynote">'
        + "".join(pages)
        + "</main></body></html>"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo-url", default="http://127.0.0.1:7860/")
    parser.add_argument("--output", type=Path, default=ROOT / "docs/keynote.html")
    args = parser.parse_args()
    html = build_keynote(args.demo_url)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(html)
    print(
        f"Generated {args.output.name}: 12 slides, recorded interactive demo, no external runtime"
    )


if __name__ == "__main__":
    main()
