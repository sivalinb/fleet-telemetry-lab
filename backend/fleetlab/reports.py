"""Portable experiment reports, generated entirely with Python and escaped HTML."""

import html
import json
from pathlib import Path
from .runs import SCENARIOS_BY_ID

ROOT = Path(__file__).resolve().parents[2]


def public_result(result):
    # Leave measured values intact; remove the workstation prefix from source paths.
    return json.loads(json.dumps(result).replace(str(ROOT) + "/", ""))


def delivery_summary(result):
    if "delivery" in result:
        d = result["delivery"]
        return [
            ("Traces received", d["traces_received"], d["traces_sent"]),
            ("Unique logs received", d["unique_logs_received"], d["logs_sent"]),
        ]
    if result.get("name") == "contract-gate":
        return [
            ("Requests blocked", result.get("blocked", 0), result.get("requested", 0))
        ]
    return [
        (
            "Complete trace chains",
            result.get("verified_chains", 0),
            result.get("requested", 0),
        ),
        (
            "Gateway logs",
            result.get("logs", {}).get("count"),
            result.get("requested", 0) * 2,
        ),
    ]


def queue_svg(result):
    samples = [s for s in result.get("samples", []) if s.get("collector")]
    if not samples:
        return "<p>No queue samples were available.</p>"
    max_x = max(1, max(s["elapsed_s"] for s in samples))
    peak = max(s["collector"].get("queued_batches", 0) for s in samples)
    max_y = max(1, peak)
    points = " ".join(
        f"{40 + 800 * s['elapsed_s'] / max_x:.1f},{190 - 140 * s['collector'].get('queued_batches', 0) / max_y:.1f}"
        for s in samples
    )
    return f'<svg viewBox="0 0 880 235" role="img" aria-label="Observed exporter queue over time"><rect width="880" height="235" rx="14" fill="#edf4fa"/><path d="M40 45V190H840" stroke="#a4b6c8" fill="none"/><polyline points="{points}" stroke="#008c96" stroke-width="3" fill="none"/><text x="40" y="25" font-family="Arial" fill="#34516d">Queue peak: {peak:g} batches · {max_x:g} seconds observed</text><text x="40" y="218" font-family="Arial" fill="#34516d">Elapsed seconds →</text></svg>'


def html_report(result):
    result = public_result(result)
    esc = lambda value: html.escape(str(value))
    scenario = SCENARIOS_BY_ID.get(result.get("name"), {})
    cards = "".join(
        f"<div><small>{esc(label)}</small><strong>{esc(value) if value is not None else 'Unavailable'} / {esc(expected)}</strong></div>"
        for label, value, expected in delivery_summary(result)
    )
    assertions = "".join(
        f"<tr><td>{esc(k.replace('_', ' '))}</td><td>{'PASS' if v else 'FAIL'}</td></tr>"
        for k, v in result.get("assertions", {}).items()
    )
    note = (
        "A passing run confirms expected loss, not loss-free delivery."
        if result.get("name")
        in {"volatile-crash", "retry-exhaustion", "queue-saturation"}
        else "Passing means the recorded assertions were met within this bounded lab run."
    )
    payload = esc(json.dumps(result, indent=2))
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Telemetry report · {esc(result.get("name"))}</title><style>body{{font:16px/1.6 system-ui,sans-serif;background:#f1f5fa;color:#17354f;margin:0}}main{{max-width:960px;margin:auto;padding:40px 24px}}header{{background:#102d4a;padding:32px;border-radius:18px;color:white}}h1{{line-height:1.15;letter-spacing:-.03em}}small{{text-transform:uppercase;letter-spacing:.09em}}.cards{{display:flex;gap:16px;margin:24px 0;flex-wrap:wrap}}.cards div{{background:white;padding:24px;border-radius:14px;flex:1;min-width:190px}}strong{{display:block;font-size:28px}}table{{width:100%;border-collapse:collapse;background:white}}td{{padding:12px;border-bottom:1px solid #d5e2ed}}svg{{width:100%;height:auto}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;background:#102d4a;color:#d8e9f5;padding:20px;border-radius:12px;font-size:12px}}@media print{{body{{background:white}}details{{display:block}}pre{{font-size:9px}}}}</style></head><body><main><header><small>Telemetry pipeline reliability lab / Python + Gradio</small><h1>{esc(scenario.get("title", result.get("name")))}</h1><p>{esc(scenario.get("question", ""))}</p><b>{esc(result.get("state", "unknown")).upper()}</b> · {esc(result.get("duration_s", "—"))} seconds</header><p>{esc(note)}</p><p><b>Hypothesis:</b> {esc(scenario.get("expected", ""))}</p><div class="cards">{cards}</div><h2>Observed queue</h2>{queue_svg(result)}<h2>Assertions</h2><table>{assertions}</table><h2>Scope</h2><p>{esc(result.get("scope", result.get("origin", "")))}</p><p>Run ID: {esc(result.get("id", ""))}. Inventory and traffic are lab data; no GPU performance is claimed.</p><details><summary>Full measured evidence</summary><pre>{payload}</pre></details></main></body></html>"""
