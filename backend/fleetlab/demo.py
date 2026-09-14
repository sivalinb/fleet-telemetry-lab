"""Gradio workbench. Every result comes from the Python API and real lab runs."""

import asyncio
import html
import json
import os
from pathlib import Path
import re
import time
import gradio as gr
import httpx
import plotly.graph_objects as go
from .contracts import resource_for
from .reports import delivery_summary, html_report, public_result
from .runs import SCENARIO_CATALOG, SCENARIOS_BY_ID, TERMINAL
from .telemetry import auth_headers

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / ".runtime/reports"
COLORS = {"navy": "#17354f", "teal": "#008c96", "red": "#c65048", "blue": "#447bc0"}
CSS = """
.gradio-container {max-width:1440px!important;margin:auto!important}
.hero {background:#102d4a;color:#edf6ff;padding:30px 34px;border-radius:20px;margin-bottom:12px;position:relative;overflow:hidden}
.hero h1 {font-size:clamp(28px,4vw,44px);line-height:1.15;letter-spacing:-.045em;margin:10px 0;color:white}
.hero p {color:#c4d8e9;max-width:800px;line-height:1.65;margin:8px 0}
.eyebrow {font:700 11px/1.6 ui-monospace,monospace;letter-spacing:.15em;text-transform:uppercase}
.hero .eyebrow {color:#68d7d1}.pill {color:#edf6ff!important;display:inline-block;padding:4px 10px;border-radius:30px;background:#204766;font-size:12px;margin:7px 5px 0 0}
.health {display:flex;gap:8px;flex-wrap:wrap;margin:8px 0 16px}.service {border:1px solid #d5e2ed;border-radius:8px;padding:7px 12px;background:#fff;color:#17354f;font-size:12px}
.dot {display:inline-block;width:7px;height:7px;border-radius:10px;background:#168e79;margin-right:7px}.down .dot {background:#c65048}
.stats {display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:12px 0}.stat {padding:16px 20px;border:1px solid #d5e2ed;border-radius:12px;background:#fff;color:#17354f}.stat b {color:#17354f;display:block;font-size:26px;letter-spacing:-.04em}.stat small {font-size:11px;color:#526f86}
.result {padding:20px 24px;background:#edf6f6;color:#17354f;border:1px solid #bededa;border-radius:14px}.result h3 {margin:0 0 8px;color:#17354f}.result p {margin:6px 0;line-height:1.55}.result code {font-size:11px}.result.issue {background:#fff5eb;border-color:#edcba4}
.empty {padding:26px;background:#f0f5fa;color:#526f86;border-radius:14px;border:1px dashed #b8cddf}.small-note {font-size:12px;color:#587087}
#scenario-panel {background:#f2f6fb;padding:20px;border-radius:16px;border:1px solid #d5e2ed}
@media(max-width:700px) {.stats {grid-template-columns:repeat(2,1fr)}.hero {padding:24px}}
"""


async def api(method, path, **kwargs):
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.request(
            method,
            os.getenv("FLEET_API_URL", "http://127.0.0.1:8001") + path,
            headers=auth_headers(),
            **kwargs,
        )
        if not response.is_success:
            try:
                message = response.json().get("detail", response.status_code)
            except ValueError:
                message = response.status_code
            raise RuntimeError(str(message))
        return response.json()


def fmt(value):
    return (
        "Unavailable"
        if value is None
        else f"{value:g}"
        if isinstance(value, (float, int))
        else html.escape(str(value))
    )


async def health_view():
    try:
        data = await api("GET", "/api/pipeline")
        services = "".join(
            f'<span class="service {"down" if s["status"] != "ready" else ""}"><i class="dot"></i>{html.escape(s["name"])} · {s["status"]}</span>'
            for s in data["services"]
        )
        c, m = data.get("collector") or {}, data["metrics"]
        values = [
            ("Main collector queue", c.get("queued_batches")),
            ("Bounded counter series", m.get("bounded_series")),
            ("Request-ID counter series", m.get("unbounded_series")),
            ("Completed service requests", m.get("completed_service_requests")),
        ]
        stats = "".join(
            f'<div class="stat"><small>{label}</small><b>{fmt(value)}</b></div>'
            for label, value in values
        )
        alerts = data.get("alerts")
        alert_text = (
            "Alert state unavailable"
            if alerts is None
            else "No active alerts"
            if not alerts
            else " · ".join(
                html.escape(a["labels"].get("alertname", "Alert"))
                + " ("
                + html.escape(a["state"])
                + ")"
                for a in alerts
            )
        )
        return f'<div class="health">{services}</div><div class="stats">{stats}</div><p class="small-note">{alert_text}. Live main-pipeline view · isolated queues appear in run evidence.</p>'
    except (httpx.HTTPError, RuntimeError, KeyError) as e:
        return f'<div class="result issue">API unavailable: {html.escape(str(e))}. Start the stack with <code>python scripts/run_stack.py</code>.</div>'


def scenario_description(name):
    s = SCENARIOS_BY_ID[name]
    return (
        f"### {s['question']}\n\n**Expected:** {s['expected']}\n\nAbout {s['seconds']} seconds. "
        + (
            "Uses an isolated collector; the main pipeline keeps running."
            if s["group"] == "isolated"
            else "Uses the gateway → scheduler → worker pipeline."
        )
    )


def base_plot(title, ytitle):
    fig = go.Figure()
    fig.update_layout(
        title=dict(text=title, font=dict(size=16)),
        template="plotly_white",
        height=285,
        margin=dict(l=45, r=20, t=50, b=40),
        font=dict(family="Arial", color=COLORS["navy"]),
        paper_bgcolor="white",
        plot_bgcolor="white",
        yaxis_title=ytitle,
        legend=dict(orientation="h", y=-0.2),
    )
    return fig


def queue_plot(result):
    fig = base_plot("Exporter backlog", "Queued requests / batches")
    samples = [s for s in result.get("samples", []) if s.get("collector")]
    if samples:
        fig.add_trace(
            go.Scatter(
                x=[s["elapsed_s"] for s in samples],
                y=[s["collector"].get("queued_batches") for s in samples],
                mode="lines+markers",
                line=dict(color=COLORS["teal"], width=3),
                fill="tozeroy",
                name="Observed queue",
                text=[s.get("phase", "") for s in samples],
            )
        )
    else:
        fig.add_annotation(
            text="Queue samples appear during a run",
            x=0.5,
            y=0.5,
            xref="paper",
            yref="paper",
            showarrow=False,
        )
    fig.update_xaxes(title="Seconds since run started")
    fig.update_yaxes(rangemode="tozero")
    return fig


def delivery_plot(result):
    fig = base_plot("Delivery evidence", "Count")
    if result.get("state") in TERMINAL:
        rows = delivery_summary(result)
        fig.add_bar(
            x=[r[0] for r in rows],
            y=[r[2] for r in rows],
            name="Input / expected",
            marker_color="#d8e4ef",
        )
        fig.add_bar(
            x=[r[0] for r in rows],
            y=[r[1] for r in rows],
            name="Measured",
            marker_color=COLORS["teal"],
        )
        fig.update_layout(barmode="group")
    else:
        fig.add_annotation(
            text="Verified backend counts appear after recovery",
            x=0.5,
            y=0.5,
            xref="paper",
            yref="paper",
            showarrow=False,
        )
    return fig


def render_result(result):
    state = result.get("state", "queued")
    heading = "Hypothesis verified" if state == "passed" else state.title()
    scenario = SCENARIOS_BY_ID[result["name"]]
    note = (
        "Expected loss is part of this experiment. Passing confirms the loss boundary; it does not mean loss-free delivery."
        if result["name"] in {"volatile-crash", "retry-exhaustion", "queue-saturation"}
        else scenario["expected"]
    )
    errors = " ".join(result.get("errors", []))
    status = f'<div class="result {"issue" if state in {"failed", "incomplete", "cancelled", "interrupted"} else ""}"><span class="eyebrow">{html.escape(scenario["title"])}</span><h3>{heading}</h3><p>{html.escape(result.get("phase", ""))} · {result.get("completed", 0)} / {result.get("requested", 0)} inputs processed</p><p>{html.escape(note)}</p><p>{html.escape(errors)}</p><code>Run {html.escape(result["id"])} · {fmt(result.get("duration_s"))} seconds</code></div>'
    checks = [
        [k.replace("_", " "), "PASS" if v else "FAIL"]
        for k, v in result.get("assertions", {}).items()
    ]
    traces = []
    for trace in result.get("traces", []):
        spans = trace.get("spans", [])
        start = min((s["start_us"] for s in spans), default=0)
        for s in spans:
            traces.append(
                [
                    trace["trace_id"],
                    s["service"],
                    s["operation"],
                    round((s["start_us"] - start) / 1000, 2),
                    round(s["duration_us"] / 1000, 2),
                ]
            )
    if "delivery" in result:
        missing = set(result["delivery"]["missing_trace_ids"])
        traces = [
            [
                t,
                "reliability-probe",
                "missing" if t in missing else "received",
                None,
                None,
            ]
            for t in result["trace_ids"]
        ]
    logs = [
        [l["timestamp"], l["body"]] for l in result.get("logs", {}).get("records", [])
    ]
    if "delivery" in result:
        missing = set(result["delivery"]["missing_event_ids"])
        logs = [
            ["missing" if event in missing else "received", event]
            for event in result["event_ids"]
        ]
    files = []
    if state in TERMINAL and re.fullmatch(r"[a-f0-9]{32}", result["id"]):
        REPORTS.mkdir(parents=True, exist_ok=True)
        for extension, content in [
            ("html", html_report(result)),
            ("json", json.dumps(public_result(result), indent=2)),
        ]:
            path = REPORTS / f"{result['id']}.{extension}"
            path.write_text(content)
            files.append(str(path))
    return (
        status,
        queue_plot(result),
        delivery_plot(result),
        checks,
        traces,
        logs,
        public_result(result),
        files,
    )


async def run_scenario(name, count):
    try:
        record = await api(
            "POST", "/api/runs", json={"name": name, "count": int(count)}
        )
        run_id = record["id"]
        deadline = time.monotonic() + 115
        while True:
            yield (run_id, *render_result(record["results"]))
            if record["state"] in TERMINAL:
                return
            if time.monotonic() > deadline:
                raise RuntimeError(
                    "Polling timed out. The saved run remains accessible in History."
                )
            await asyncio.sleep(0.8)
            record = await api("GET", "/api/runs/" + run_id)
    except (httpx.HTTPError, RuntimeError) as error:
        raise gr.Error(str(error)) from error


async def cancel_run(run_id):
    if not run_id:
        return "No run selected."
    try:
        record = await api("POST", "/api/runs/" + run_id + "/cancel")
        return "Run " + record["state"] + ". Its evidence remains in History."
    except (httpx.HTTPError, RuntimeError) as error:
        return str(error)


async def history():
    try:
        records = await api("GET", "/api/experiments")
        choices = [
            (f"{r['name']} · {r['state']} · {r['id'][:8]}", r["id"]) for r in records
        ]
        rows = []
        for r in records:
            d = r["results"].get("delivery", {})
            rows.append(
                [
                    r["name"],
                    r["state"],
                    r["results"].get("requested"),
                    d.get("traces_received", r["results"].get("verified_chains")),
                    d.get(
                        "unique_logs_received",
                        r["results"].get("logs", {}).get("count"),
                    ),
                    r["results"].get("duration_s"),
                    r["id"][:8],
                ]
            )
        return gr.update(
            choices=choices, value=choices[0][1] if choices else None
        ), rows
    except (httpx.HTTPError, RuntimeError) as error:
        raise gr.Error(str(error)) from error


async def load_run(run_id):
    if not run_id:
        raise gr.Error("Choose a saved run first.")
    result = (await api("GET", "/api/runs/" + run_id))["results"]
    return (run_id, *render_result(result))


async def contract_check(resource, attributes):
    try:
        resource = json.loads(resource) if isinstance(resource, str) else resource
        attributes = (
            json.loads(attributes) if isinstance(attributes, str) else attributes
        )
    except ValueError as error:
        raise gr.Error("Enter valid JSON in both editors.") from error
    if not isinstance(resource, dict) or not isinstance(attributes, dict):
        raise gr.Error("Resource and metric attributes must be JSON objects.")
    try:
        return await api(
            "POST",
            "/api/contract",
            json={"resource": resource, "attributes": attributes},
        )
    except (httpx.HTTPError, RuntimeError) as error:
        raise gr.Error(str(error)) from error


def build_demo():
    with gr.Blocks(
        title="Telemetry Reliability Lab",
        analytics_enabled=False,
        fill_width=True,
        delete_cache=(3600, 3600),
    ) as demo:
        gr.HTML(
            '<div class="hero"><div class="eyebrow">Infrastructure field lab / 03</div><h1>Follow every signal.<br>Find where it breaks.</h1><p>Send real telemetry, introduce a controlled failure, and inspect what arrives. Nine experiments connect instrumentation choices to delivery, loss, and recovery.</p><span class="pill">Python + Gradio</span><span class="pill">OpenTelemetry</span><span class="pill">Real backend evidence</span><span class="pill">CPU lab · no GPU required</span></div>'
        )
        live = gr.HTML('<div class="empty">Checking the local pipeline…</div>')
        gr.Timer(4).tick(
            health_view,
            outputs=live,
            queue=False,
            api_name=False,
            show_progress="hidden",
        )
        demo.load(health_view, outputs=live, api_name="pipeline_status")
        selected_run = gr.State("")
        with gr.Tabs():
            with gr.Tab("Run an experiment"):
                with gr.Row(equal_height=False):
                    with gr.Column(scale=1, min_width=285, elem_id="scenario-panel"):
                        gr.Markdown("### Choose a failure boundary")
                        scenario = gr.Dropdown(
                            choices=[(s["title"], s["id"]) for s in SCENARIO_CATALOG],
                            value="durable-crash",
                            label="Experiment",
                        )
                        description = gr.Markdown(scenario_description("durable-crash"))
                        count = gr.Slider(
                            8,
                            40,
                            value=12,
                            step=1,
                            label="Logical inputs",
                            info="Each isolated input emits one trace and one log.",
                        )
                        run = gr.Button("Run experiment", variant="primary", size="lg")
                        cancel = gr.Button("Cancel active run", variant="secondary")
                        cancel_message = gr.Markdown()
                        gr.Markdown(
                            "One experiment runs at a time. Results are saved in the API database, so closing this page does not stop a run."
                        )
                    with gr.Column(scale=3, min_width=400):
                        status = gr.HTML(
                            '<div class="empty"><b>Your experiment starts here.</b><p>Try the persistent queue crash, then compare it with the in-memory queue. Both runs send real signals and record exactly what was recovered.</p></div>'
                        )
                        with gr.Row():
                            queue = gr.Plot(queue_plot({}), show_label=False)
                            delivery = gr.Plot(delivery_plot({}), show_label=False)
                        assertions = gr.Dataframe(
                            headers=["Assertion", "Result"],
                            value=[],
                            label="What the experiment proved",
                            interactive=False,
                            wrap=True,
                        )
                        with gr.Accordion("Trace and log evidence", open=False):
                            trace_table = gr.Dataframe(
                                headers=[
                                    "Trace ID",
                                    "Service",
                                    "Operation / delivery",
                                    "Start ms",
                                    "Duration ms",
                                ],
                                value=[],
                                interactive=False,
                                label="Trace spans or isolated probe delivery",
                                max_height=330,
                            )
                            log_table = gr.Dataframe(
                                headers=["Timestamp / delivery", "Log body / event ID"],
                                value=[],
                                interactive=False,
                                label="Correlated logs",
                                max_height=280,
                            )
                        with gr.Accordion("Raw measurements", open=False):
                            raw = gr.JSON(label="Saved evidence")
                        downloads = gr.File(
                            label="Download the illustrated HTML report and JSON evidence",
                            file_count="multiple",
                            interactive=False,
                        )
            with gr.Tab("History & comparison"):
                gr.Markdown(
                    "### Keep the evidence, compare the tradeoffs\nRows are measured runs. Workload runs count complete three-service traces and gateway logs; isolated runs count unique probe signals. Expected-loss experiments can pass with missing originals."
                )
                refresh = gr.Button("Refresh saved runs")
                history_table = gr.Dataframe(
                    headers=[
                        "Experiment",
                        "State",
                        "Inputs",
                        "Traces / chains",
                        "Logs",
                        "Seconds",
                        "Run ID",
                    ],
                    interactive=False,
                    value=[],
                    wrap=True,
                )
                saved = gr.Dropdown(label="Saved run", choices=[])
                load = gr.Button("Load evidence into experiment tab", variant="primary")
            with gr.Tab("Instrumentation contract"):
                gr.Markdown(
                    "### Keep identity in the right signal\nThis explicit Python contract requires five resource fields and rejects high-cardinality metric attributes. Try removing `request_id` from the attributes to pass validation. The workload gate uses the same function."
                )
                with gr.Row():
                    resource = gr.Code(
                        language="json",
                        value=json.dumps(resource_for("gateway"), indent=2),
                        label="Resource attributes",
                        interactive=True,
                    )
                    attributes = gr.Code(
                        language="json",
                        value=json.dumps(
                            {"profile": "bounded", "request_id": "one-per-request"},
                            indent=2,
                        ),
                        label="Metric attributes",
                        interactive=True,
                    )
                check = gr.Button("Validate instrumentation", variant="primary")
                contract_result = gr.JSON(label="Contract result")
            with gr.Tab("Architecture & field guide"):
                asset = ROOT / "docs/assets/telemetry.svg"
                if asset.exists():
                    gr.HTML(asset.read_text())
                gr.Markdown("""### What this lab solves
Telemetry can be accepted upstream and still be lost later. This lab makes the boundaries observable: SDK export, collector queueing, retry exhaustion, process crashes, and backend indexing.

**Main path:** Python gateway → scheduler → worker → OpenTelemetry Collector → Prometheus, Loki, Jaeger. A Python relay injects short export outages.

**Isolated path:** Python probes → a temporary Collector + relay → the same Loki and Jaeger. Each run owns its subprocesses, queue directory, and ports. A recovery canary confirms the backend is working when originals are missing.

**Scope:** Small, bounded experiments with real HTTP and OTLP. This is not a GPU benchmark or a guarantee of exactly-once delivery. A persistent queue protects only data already in that queue; disk failures and upstream buffers remain separate risks.

**Scaling next:** Multiple collectors by failure domain; durable storage sized from measured ingestion rate and outage budget; independent signal backends; a durable job queue and worker leases before running multiple API workers. See the field guide for capacity arithmetic, operational runbooks, and an extension plan.
""")
                base = os.getenv("PUBLIC_API_URL", "http://127.0.0.1:8001")
                gr.Markdown(
                    f"[Open the illustrated field guide]({base}/docs-guide/field-guide.html) · [API reference]({base}/docs) · [Source on GitHub](https://github.com/sivalinb/fleet-telemetry-lab)"
                )
        outputs = [
            selected_run,
            status,
            queue,
            delivery,
            assertions,
            trace_table,
            log_table,
            raw,
            downloads,
        ]
        scenario.change(scenario_description, scenario, description, api_name=False)
        run.click(
            run_scenario,
            [scenario, count],
            outputs,
            api_name="run_experiment",
            concurrency_limit=1,
            concurrency_id="run",
        )
        cancel.click(
            cancel_run, selected_run, cancel_message, queue=False, api_name=False
        )
        refresh.click(history, outputs=[saved, history_table], api_name="saved_runs")
        load.click(load_run, saved, outputs, api_name="load_run")
        check.click(
            contract_check,
            [resource, attributes],
            contract_result,
            api_name="validate_contract",
        )
    return demo


def main():
    REPORTS.mkdir(parents=True, exist_ok=True)
    theme = gr.themes.Soft(
        primary_hue="teal",
        secondary_hue="blue",
        neutral_hue="slate",
        font=["Arial", "sans-serif"],
        font_mono=["ui-monospace", "monospace"],
    )
    theme.set(
        block_label_text_color="#28526b",
        block_title_text_color="#17354f",
        button_primary_background_fill="#007b80",
        button_primary_background_fill_hover="#006b70",
        button_primary_text_color="white",
    )
    # Keep the workbench palette consistent with its inline evidence cards.
    values = theme.to_dict()["theme"]
    theme.set(
        **{
            key: values[key.removesuffix("_dark")]
            for key in values
            if key.endswith("_dark") and key.removesuffix("_dark") in values
        }
    )
    build_demo().queue(default_concurrency_limit=4).launch(
        server_name=os.getenv("GRADIO_SERVER_NAME", "127.0.0.1"),
        server_port=int(os.getenv("GRADIO_SERVER_PORT", "7860")),
        share=False,
        ssr_mode=False,
        enable_monitoring=False,
        footer_links=[],
        run_history=False,
        allowed_paths=[str(REPORTS)],
        max_file_size="4mb",
        theme=theme,
        css=CSS,
    )


if __name__ == "__main__":
    main()
