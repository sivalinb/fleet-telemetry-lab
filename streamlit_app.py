"""The complete demo UI is Python/Streamlit; no custom JavaScript frontend."""

from pathlib import Path
import html
import json
import os
import re
import urllib.parse
import httpx
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parent
API = os.getenv("FLEET_API_URL", "http://127.0.0.1:8001").rstrip("/")
PUBLIC_API = os.getenv("FLEET_PUBLIC_API_URL", "http://127.0.0.1:8001").rstrip("/")
st.set_page_config(
    page_title="Fleet Atlas · Catalog & Signal Lab",
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="collapsed",
)


def request(path, body=None, raw=False):
    token = os.getenv("LAB_API_TOKEN", "")
    headers = {"Authorization": "Bearer " + token} if token else {}
    with httpx.Client(timeout=75, headers=headers) as client:
        r = (
            client.get(API + path)
            if body is None
            else client.post(API + path, json=body)
        )
        r.raise_for_status()
        return r.text if raw else r.json()


def esc(value):
    return html.escape(str(value))


st.html("""<style>
header[data-testid="stHeader"] {background:transparent; height:2.8rem}
.block-container {padding:3.4rem 2.8rem 3rem; max-width:1600px}
body, p, [data-testid="stMarkdownContainer"] {font-size:16px}
h1,h2,h3 {letter-spacing:-.035em}
h1 {font-weight:750!important}
button {border-radius:10px!important}
div[data-testid="stMetric"] {background:white;border:1px solid #dbe5f2;border-radius:14px;padding:16px 20px;min-height:104px}
div[data-testid="stMetricLabel"] {color:#52708c;font-size:14px;text-transform:uppercase;letter-spacing:.06em}
div[data-testid="stMetricValue"] {color:#102b4c;font-weight:700}
div[data-testid="stVerticalBlockBorderWrapper"] {border-radius:14px}
.mast {display:flex;align-items:center;justify-content:space-between;margin-bottom:20px;gap:20px}
.brand {display:flex;align-items:center;gap:14px;color:#142e4e;font-size:23px;font-weight:750;letter-spacing:-.04em}
.mark {display:grid;place-items:center;background:#142e4e;color:#6ee6d5;border-radius:12px;width:44px;height:44px;font-size:30px}
.eyebrow {font-size:12px;text-transform:uppercase;letter-spacing:.15em;color:#53728c;font-weight:650}
.tag {padding:7px 12px;border:1px solid #c8d6e7;border-radius:25px;font-size:13px;color:#385771;background:#fff;white-space:nowrap}
.entity-card {background:#112b49;color:#eaf3ff;padding:24px;border-radius:15px;min-height:190px}
.entity-card h3 {color:white;font-size:27px;margin:6px 0 10px}
.entity-card p {color:#b9d1e9;font-size:14px;margin:8px 0}
.tiny {font-size:13px;color:#6b829a}
.pill {padding:5px 9px;background:#e6f5f0;color:#147563;border-radius:7px;font-size:13px}
.source {display:flex;justify-content:space-between;align-items:center;padding:13px 0;border-bottom:1px solid #e1e9f3;gap:12px}
.flow {display:flex;align-items:stretch;gap:10px;margin:14px 0 24px;flex-wrap:wrap}
.flowbox {flex:1;min-width:140px;background:white;border:1px solid #d8e3f0;padding:16px;border-radius:12px}
.flowbox b {display:block;color:#173658;margin-bottom:6px}
.flowbox small {font-size:13px;color:#69829b}
.legend {display:flex;gap:16px;flex-wrap:wrap;font-size:13px;color:#58718c}
.guide-intro {background:#102a48;color:#e7f4ff;padding:30px;border-radius:16px;margin:18px 0}
.guide-intro h2 {color:#fff;margin-top:0}
@media(max-width:700px){.block-container{padding:3.4rem 1rem 2rem}.mast{align-items:flex-start}.tag{white-space:normal}.brand{font-size:21px}}
@media(prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
</style>""")
st.html(
    '<div class="mast"><div class="brand"><span class="mark">◈</span><span>Fleet Atlas<div class="eyebrow">Infrastructure, connected.</div></span></div><span class="tag">Python · Streamlit · OpenTelemetry</span></div>'
)
view = st.segmented_control(
    "Workspace",
    ["Fleet catalog", "Signal lab", "Field guide"],
    default="Fleet catalog",
    label_visibility="collapsed",
    key="workspace",
)


def catalog_graph(data, selected):
    colors = {
        "cluster": "#143759",
        "rack": "#5683b0",
        "node": "#159eaa",
        "service": "#7762d4",
        "team": "#c1882b",
    }
    levels = ["cluster", "rack", "node", "service", "team"]
    positions = {}
    for x, kind in enumerate(levels):
        items = [e for e in data["entities"] if e["kind"] == kind]
        for j, e in enumerate(items):
            positions[e["id"]] = (x, (j + 1) / (len(items) + 1) * 12)
    fig = go.Figure()
    for edge in data["edges"]:
        if edge["source"] not in positions or edge["target"] not in positions:
            continue
        a, b = positions[edge["source"]], positions[edge["target"]]
        active = selected in {edge["source"], edge["target"]}
        fig.add_trace(
            go.Scatter(
                x=[a[0], b[0]],
                y=[a[1], b[1]],
                mode="lines",
                line={
                    "color": "#087fbd" if active else "#d9e3ee",
                    "width": 2.8 if active else 1,
                },
                hoverinfo="skip",
                showlegend=False,
            )
        )
    for kind in levels:
        items = [e for e in data["entities"] if e["kind"] == kind]
        fig.add_trace(
            go.Scatter(
                x=[positions[e["id"]][0] for e in items],
                y=[positions[e["id"]][1] for e in items],
                mode="markers+text",
                text=[e.get("name", e["id"]).split(" · ")[0] for e in items],
                textposition="middle right" if kind != "team" else "middle left",
                textfont={"size": 11, "color": "#304d6d"},
                customdata=[e["id"] for e in items],
                hovertext=[
                    f"{e.get('name', e['id'])}<br>{e['kind']} · {len(e['issues'])} data-quality findings"
                    for e in items
                ],
                hovertemplate="%{hovertext}<extra></extra>",
                marker={
                    "size": [22 if e["id"] == selected else 13 for e in items],
                    "color": [
                        "#e79736" if e.get("health") == "degraded" else colors[kind]
                        for e in items
                    ],
                    "line": {"width": 2, "color": "white"},
                    "symbol": "square" if kind in {"cluster", "rack"} else "circle",
                },
                name=kind.title(),
            )
        )
    fig.update_layout(
        height=490,
        margin={"l": 12, "r": 10, "t": 30, "b": 10},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"family": "Arial"},
        showlegend=False,
        clickmode="event+select",
        dragmode="pan",
        xaxis={
            "range": [-0.18, 4.25],
            "tickvals": list(range(5)),
            "ticktext": ["CLUSTERS", "RACKS", "NODES", "SERVICES", "TEAMS"],
            "side": "top",
            "showgrid": False,
            "zeroline": False,
            "fixedrange": True,
            "tickfont": {"size": 12, "color": "#688199"},
        },
        yaxis={"range": [0, 12.6], "visible": False, "fixedrange": True},
    )
    return fig


def graph_click():
    value = st.session_state.get("fleetgraph", {})
    points = value.get("selection", {}).get("points", [])
    if points and points[-1].get("customdata"):
        st.session_state.entity_picker = points[-1]["customdata"]


def show_catalog():
    try:
        data = request("/api/catalog")
    except (httpx.HTTPError, ValueError):
        st.error(
            "The catalog API is unavailable. Start the Python stack to load the fleet. Your saved inventory is retained."
        )
        st.code("python scripts/run_stack.py", language="bash")
        return
    st.title("Know what you operate.")
    st.caption(
        "A fictional fleet with real source reconciliation, dependency discovery, and durable history."
    )
    entities = data["entities"]
    byid = {e["id"]: e for e in entities}
    cols = st.columns(4)
    cols[0].metric("Fleet objects", len(entities))
    cols[1].metric("Modeled GPUs", sum(e.get("gpus", 0) for e in entities))
    cols[2].metric("Owning teams", sum(e["kind"] == "team" for e in entities))
    cols[3].metric("Open data checks", sum(len(e["issues"]) for e in entities))
    st.write("")
    c1, c2, c3 = st.columns([2, 1.3, 1])
    if "entity_picker" not in st.session_state:
        st.session_state.entity_picker = "node:FTL-A11"
    selected = c1.selectbox(
        "Inspect an entity",
        list(byid),
        format_func=lambda x: f"{byid[x]['kind'].title()} · {byid[x].get('name', x)}",
        key="entity_picker",
    )
    choices = {
        "Healthy baseline": "refresh",
        "Ownership conflict": "ownership-conflict",
        "Source goes quiet": "stale-source",
        "Node degrades": "node-degraded",
        "Source drops a node": "missing-node",
    }
    chosen = c2.selectbox("Explore a scenario", list(choices))
    c3.write("")
    c3.write("")
    if c3.button("Apply scenario", type="primary", width="stretch"):
        try:
            request("/api/catalog/scenarios/" + choices[chosen], {})
            st.rerun()
        except httpx.HTTPError as e:
            st.error("Could not apply the scenario: " + str(e))
    left, right = st.columns([2.1, 1], gap="large")
    with left:
        with st.container(border=True):
            st.subheader("Fleet topology", anchor=False)
            st.caption(
                "Select a point or use the entity picker. Lines show recorded relationships."
            )
            st.plotly_chart(
                catalog_graph(data, selected),
                key="fleetgraph",
                on_select=graph_click,
                selection_mode="points",
                config={"displayModeBar": False},
                width="stretch",
                theme=None,
            )
            st.html(
                '<div class="legend"><span>■ Location</span><span style="color:#159eaa">● Compute</span><span style="color:#7762d4">● Service</span><span style="color:#c1882b">● Team</span></div>'
            )
    with right:
        e = byid[selected]
        owner = byid.get(e.get("owner"), {})
        st.html(
            f'<div class="entity-card"><div class="eyebrow" style="color:#77cce4">{esc(e["kind"])} / {esc(e.get("health", "cataloged"))}</div><h3>{esc(e.get("name", selected))}</h3><p>{esc(selected)}</p><p>Owner · {esc(owner.get("name", "Not recorded"))}</p><p>{esc(owner.get("oncall", e.get("description", "Source-linked infrastructure record")))}</p></div>'
        )
        impact = request("/api/impact/" + urllib.parse.quote(selected, safe=""))
        st.subheader("Dependency exposure", anchor=False)
        if impact["services"]:
            for service in impact["services"]:
                st.markdown(
                    f"**{service.get('name', service['id'])}**  \n{byid.get(service.get('owner'), {}).get('name', 'Owner missing')}"
                )
        else:
            st.caption("No downstream services are recorded for this entity.")
        st.caption(impact["interpretation"])
        if e.get("runbook"):
            st.link_button(
                "Open runbook",
                PUBLIC_API + e["runbook"]
                if e["runbook"].startswith("/")
                else e["runbook"],
            )
        for issue in e["issues"]:
            (st.error if issue["severity"] == "critical" else st.warning)(
                issue["message"]
            )
    bottom1, bottom2 = st.columns([1, 2])
    with bottom1:
        st.subheader("Source freshness", anchor=False)
        for source in data["sources"]:
            age = source["age_seconds"]
            label = (
                "Never synced"
                if age is None
                else (f"{age // 60}m ago" if age >= 60 else f"{age}s ago")
            )
            color = "#bf6b1e" if source["stale"] else "#157c6b"
            st.html(
                f'<div class="source"><span><b>{esc(source["name"])}</b><br><span class="tiny">TTL {source["ttl_seconds"] // 60}m · {esc(label)}</span></span><span style="color:{color}">{"Stale" if source["stale"] else "Current"}</span></div>'
            )
    with bottom2:
        st.subheader("Why this value?", anchor=False)
        st.caption(
            "Each resolved field retains its source and observation time. Ownership conflicts remain visible."
        )
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Field": k,
                        "Value": json.dumps(e.get(k))
                        if isinstance(e.get(k), (list, dict))
                        else str(e.get(k, "")),
                        "Source": v["source"],
                        "Observed": v["observed_at"][:19],
                    }
                    for k, v in e["provenance"].items()
                ]
            ),
            hide_index=True,
            width="stretch",
        )
    with st.expander("Inventory table, exports, and lifecycle history"):
        search = st.text_input("Find a record by name, identifier, or owner")
        records = [
            {
                "Entity": e.get("name", e["id"]),
                "Identifier": e["id"],
                "Kind": e["kind"],
                "Owner": e.get("owner", ""),
                "Checks": len(e["issues"]),
            }
            for e in entities
        ]
        st.dataframe(
            pd.DataFrame(
                [r for r in records if search.lower() in json.dumps(r).lower()]
            ),
            hide_index=True,
            width="stretch",
        )
        a, b = st.columns(2)
        a.download_button(
            "Download catalog JSON",
            json.dumps(data, indent=2),
            "fleet-catalog.json",
            "application/json",
            width="stretch",
        )
        b.download_button(
            "Download Backstage YAML",
            request("/api/catalog/export/backstage", raw=True),
            "catalog-info.yaml",
            "application/yaml",
            width="stretch",
        )
        audit = request("/api/audit")
        st.dataframe(pd.DataFrame(audit), hide_index=True, width="stretch")


def show_lab():
    st.title("Follow the signal. Break the pipeline.")
    st.caption(
        "Real Python HTTP requests produce correlated metrics, logs, and traces. GPU behavior is not simulated as benchmark evidence."
    )
    try:
        status = request("/api/pipeline")
    except httpx.HTTPError:
        st.error(
            "The lab API is unavailable. Start the Python stack to run experiments."
        )
        return
    ready = {s["name"]: s["status"] == "ready" for s in status["services"]}
    st.html(
        '<div class="flow">'
        + "".join(
            f'<div class="flowbox"><b>{label}</b><small>{description}</small><p style="margin:8px 0 0;color:{"#138370" if ready.get(key) else "#b67834"}">{"Connected" if ready.get(key) else "Unavailable"}</p></div>'
            for key, label, description in [
                ("gateway", "01 · Python services", "Gateway → scheduler → worker"),
                ("collector", "02 · OTel Collector", "Batching + persistent queues"),
                ("relay", "03 · Fault relay", "A controlled backend outage"),
                ("prometheus", "04 · Metrics", "Prometheus time series"),
                ("loki", "05 · Logs", "Loki structured events"),
                ("jaeger", "06 · Traces", "Jaeger request journeys"),
            ]
        )
        + "</div>"
    )
    counters = status.get("collector") or {}
    metric = status["metrics"]
    c = st.columns(4)
    c[0].metric(
        "Service requests",
        "—"
        if metric["completed_service_requests"] is None
        else int(metric["completed_service_requests"]),
    )
    c[1].metric(
        "Queued batches", "—" if not counters else int(counters["queued_batches"])
    )
    c[2].metric(
        "Bounded series",
        "—" if metric["bounded_series"] is None else int(metric["bounded_series"]),
    )
    c[3].metric(
        "Unbounded series",
        "—" if metric["unbounded_series"] is None else int(metric["unbounded_series"]),
    )
    st.caption(
        "Metrics cover the three current workload processes. A dash means no measurement is available. Old process series remain in Prometheus until they expire."
    )
    experiments = {
        "Baseline": "baseline",
        "Label growth": "label-growth",
        "Contract gate": "contract-gate",
        "Slow worker": "slow-worker",
        "Backend outage": "backend-outage",
    }
    explain = {
        "Baseline": "Send requests across three Python services and verify the correlated logs and complete traces.",
        "Label growth": "Deliberately add a unique request_id metric label for a bounded test, then measure the extra series.",
        "Contract gate": "Submit the same unbounded label to the instrumentation contract. Requests should be rejected before any work is emitted.",
        "Slow worker": "Add 180 ms at the worker and inspect where that time appears in the distributed trace.",
        "Backend outage": "Return HTTP 503 to trace and log exports for eight seconds. Observe retries, queueing, and eventual delivery.",
    }
    a, b, c = st.columns([2, 1, 1])
    chosen = a.selectbox("Experiment", list(experiments))
    count = b.number_input("Requests", min_value=4, max_value=40, value=12, step=4)
    c.write("")
    c.write("")
    if c.button(
        "Run experiment",
        type="primary",
        width="stretch",
        disabled=not all(ready.values()),
    ):
        with st.spinner("Running the workload and checking exported evidence…"):
            try:
                result = request(
                    "/api/experiments", {"name": experiments[chosen], "count": count}
                )
                st.session_state.last_experiment = result["id"]
                st.rerun()
            except httpx.HTTPError as error:
                st.error(str(error))
    st.info(explain[chosen])
    if not all(ready.values()):
        st.warning(
            "Start all observability services to enable experiments. The catalog can run independently."
        )
    if st.button("Refresh measurements"):
        st.rerun()
    saved = request("/api/experiments")
    if not saved:
        st.markdown(
            "**Your first experiment** will create a saved evidence record here, including request counts, trace IDs, queue samples, and log excerpts."
        )
        return
    ids = [e["id"] for e in saved]
    index = (
        ids.index(st.session_state.last_experiment)
        if st.session_state.get("last_experiment") in ids
        else 0
    )
    chosen_id = st.selectbox(
        "Saved experiment",
        ids,
        index=index,
        format_func=lambda x: next(
            f"{e['name']} · {e['state']} · {e['created_at'][:19]}"
            for e in saved
            if e["id"] == x
        ),
    )
    run = next(e["results"] for e in saved if e["id"] == chosen_id)
    if run.get("state") == "passed":
        st.success("The experiment met its delivery or contract assertions.")
    else:
        st.warning(
            "Some assertions are incomplete or failed. Inspect the recorded evidence below."
        )
    cols = st.columns(4)
    cols[0].metric(
        "Requests completed", f"{run.get('completed', 0)} / {run.get('requested', 0)}"
    )
    cols[1].metric("Complete trace chains", run.get("verified_chains", 0))
    cols[2].metric(
        "Gateway log records",
        run.get("logs", {}).get("count")
        if run.get("logs", {}).get("count") is not None
        else "—",
    )
    cols[3].metric("Contract rejections", run.get("blocked", 0))
    l, r = st.columns(2)
    with l:
        st.subheader("Trace waterfall", anchor=False)
        traces = [t for t in run.get("traces", []) if t.get("spans")]
        if traces:
            t = traces[0]
            base = min(s["start_us"] for s in t["spans"])
            fig = go.Figure()
            for span in sorted(t["spans"], key=lambda s: s["start_us"]):
                fig.add_trace(
                    go.Bar(
                        name=span["service"],
                        y=[span["service"]],
                        x=[span["duration_us"] / 1000],
                        base=[(span["start_us"] - base) / 1000],
                        orientation="h",
                        marker_color={
                            "gateway": "#168ec0",
                            "scheduler": "#7966d5",
                            "worker": "#20aa99",
                        }.get(span["service"], "#627996"),
                        hovertemplate="%{x:.2f} ms<extra>%{y}</extra>",
                    )
                )
            fig.update_layout(
                height=270,
                showlegend=False,
                xaxis_title="Milliseconds from request start",
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                margin={"l": 5, "r": 15, "t": 20, "b": 20},
            )
            st.plotly_chart(fig, width="stretch", theme=None)
            st.code(t["trace_id"], language=None)
        else:
            st.caption("No trace was expected or no complete trace was retrieved.")
    with r:
        st.subheader("Collector queue", anchor=False)
        samples = [
            {
                "Elapsed seconds": s["elapsed_s"],
                "Queued batches": s["collector"]["queued_batches"],
            }
            for s in run.get("samples", [])
            if s.get("collector")
        ]
        if samples:
            st.line_chart(
                pd.DataFrame(samples).set_index("Elapsed seconds"),
                color="#087fbd",
                height=270,
            )
        else:
            st.caption("Collector samples were unavailable for this run.")
    with st.expander("Log evidence and full experiment record"):
        st.dataframe(
            pd.DataFrame(run.get("logs", {}).get("records", [])),
            width="stretch",
            hide_index=True,
        )
        if run.get("errors"):
            st.error("\n".join(run["errors"]))
        st.json(run, expanded=False)
        st.download_button(
            "Download experiment evidence",
            json.dumps(run, indent=2),
            f"experiment-{chosen_id}.json",
            "application/json",
        )


def show_guide():
    st.title("The field guide")
    st.caption(
        "Architecture, design decisions, test evidence, scaling, and a practical extension plan."
    )
    sections = {
        "What it does": "OVERVIEW.md",
        "Architecture": "ARCHITECTURE.md",
        "Technologies": "TECHNOLOGIES.md",
        "Test cases": "TESTING.md",
        "Scaling": "SCALING.md",
        "Extension plan": "ROADMAP.md",
        "Runbooks": "RUNBOOKS.md",
    }
    section = st.selectbox("Read a chapter", list(sections))
    if section == "What it does":
        st.image(str(ROOT / "docs/assets/architecture.svg"), width="stretch")
    file = ROOT / "docs" / sections[section]
    if file.exists():
        for part in re.split(r"(!\[[^\]]*\]\(assets/[^)]+\))", file.read_text()):
            diagram = re.fullmatch(r"!\[[^\]]*\]\((assets/[^)]+)\)", part)
            if diagram:
                st.image(str(ROOT / "docs" / diagram.group(1)), width="stretch")
            elif part.strip():
                part = part.replace(
                    "(../evidence/README.md)",
                    "(https://github.com/sivalinb/fleet-telemetry-lab/tree/main/evidence)",
                )
                st.markdown(part)
    else:
        st.error("The guide file is missing. Restore docs/ from the repository.")


if view == "Fleet catalog":
    show_catalog()
elif view == "Signal lab":
    show_lab()
else:
    show_guide()
st.divider()
st.caption(
    "Fleet Atlas · Built by Siva Babu · Fictional infrastructure, inspectable engineering. All application code is Python."
)
