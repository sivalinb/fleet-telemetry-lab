"""Generate editable SVG diagrams and a standalone illustrated HTML guide in Python."""

from html import escape
from pathlib import Path
import re
import markdown

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "docs/assets"
NAVY = "#102d4a"
TEAL = "#007f86"
BLUE = "#2466be"
PURPLE = "#7055bb"
MUTED = "#5b738d"


class Diagram:
    def __init__(self, title, subtitle, height=760):
        self.h = height
        self.parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 {height}" role="img" aria-label="{escape(title)}"><defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#8096ac"/></marker></defs><rect width="1280" height="{height}" rx="24" fill="#f1f6fc"/>'
        ]
        self.text(48, 48, "FLEET ATLAS  /  ENGINEERING FIELD GUIDE", 12, MUTED, 700)
        self.text(48, 96, title, 34, NAVY, 700)
        self.text(48, 128, subtitle, 17, MUTED)

    def text(self, x, y, value, size=17, color=NAVY, weight=400):
        self.parts.append(
            f'<text x="{x}" y="{y}" font-family="Arial, sans-serif" font-size="{size}" fill="{color}" font-weight="{weight}">{escape(value)}</text>'
        )

    def rect(self, x, y, w, h, color="#fff", stroke="#d4e0ee"):
        self.parts.append(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="16" fill="{color}" stroke="{stroke}"/>'
        )

    def card(self, x, y, w, h, kicker, title, lines, color=BLUE):
        self.rect(x, y, w, h)
        self.parts.append(
            f'<rect x="{x + 1}" y="{y + 18}" width="4" height="{h - 36}" rx="2" fill="{color}"/>'
        )
        self.text(x + 20, y + 29, kicker, 11, color, 700)
        self.text(
            x + 20,
            y + 58,
            title,
            min(21, (w - 40) / max(len(title) * 0.54, 1)),
            NAVY,
            700,
        )
        for i, line in enumerate(lines):
            self.text(x + 20, y + 85 + i * 23, line, 15, MUTED)

    def arrow(self, x1, y1, x2, y2, label=None):
        self.parts.append(
            f'<path d="M{x1} {y1} L{x2} {y2}" fill="none" stroke="#8096ac" stroke-width="2" marker-end="url(#arrow)"/>'
        )
        if label:
            self.text((x1 + x2) / 2 - 25, (y1 + y2) / 2 - 9, label, 12, MUTED)

    def footer(self, value):
        self.text(48, self.h - 26, value, 13, MUTED)

    def save(self, name):
        ASSETS.mkdir(parents=True, exist_ok=True)
        (ASSETS / name).write_text("".join(self.parts) + "</svg>")


def diagrams():
    d = Diagram(
        "Know the fleet. Verify the signal.",
        "Two Python projects, one Streamlit workspace. Fictional infrastructure; real telemetry delivery.",
        980,
    )
    d.text(48, 179, "01  /  FLEET CATALOG", 14, TEAL, 700)
    d.card(
        48,
        200,
        265,
        180,
        "OBSERVE",
        "Source snapshots",
        [
            "Service catalog ownership",
            "Kubernetes node / service data",
            "Redfish identity / hardware",
        ],
        TEAL,
    )
    d.card(
        365,
        200,
        265,
        180,
        "RECONCILE",
        "Python + FastAPI",
        [
            "Validate + replay protection",
            "Field priority + provenance",
            "Conflicts, freshness, absence",
        ],
        TEAL,
    )
    d.card(
        685,
        200,
        260,
        180,
        "RETAIN",
        "SQL catalog",
        [
            "Sources + observations",
            "Entities + sync runs + audit",
            "SQLite / PostgreSQL",
        ],
        TEAL,
    )
    d.arrow(313, 286, 365, 286)
    d.arrow(630, 286, 685, 286)
    d.text(48, 431, "02  /  SIGNAL LAB", 14, BLUE, 700)
    d.card(
        48,
        450,
        265,
        180,
        "GENERATE",
        "Three Python services",
        [
            "Gateway → scheduler → worker",
            "W3C traces + structured logs",
            "Counters + duration histograms",
        ],
    )
    d.card(
        365,
        450,
        265,
        180,
        "COLLECT",
        "OTel Collector",
        ["OTLP / HTTP + batching", "Memory limiter", "Persistent log / trace queues"],
    )
    d.card(
        685,
        450,
        260,
        180,
        "EXERCISE",
        "Python fault relay",
        ["Time-bounded HTTP 503", "Real exporter retries", "Original OTLP payloads"],
    )
    d.arrow(313, 538, 365, 538)
    d.arrow(630, 538, 685, 538)
    d.card(
        48,
        685,
        265,
        165,
        "MEASURE",
        "Prometheus",
        ["Scrapes workload counters", "And Collector self-metrics"],
    )
    d.card(
        365,
        685,
        265,
        165,
        "INVESTIGATE",
        "Loki + Jaeger",
        ["Logs by experiment identifier", "Trace chain + span duration"],
    )
    d.card(
        685,
        685,
        260,
        165,
        "PROVE",
        "Python experiment runner",
        ["Assertions + bounded polling", "Evidence saved to SQL"],
    )
    d.arrow(495, 630, 185, 685)
    d.arrow(817, 630, 500, 685)
    d.arrow(630, 768, 685, 768)
    d.rect(995, 200, 237, 650, NAVY, NAVY)
    d.text(1017, 238, "03  /  DISCOVER", 12, "#80ddd7", 700)
    d.text(1017, 280, "Streamlit", 29, "#fff", 700)
    d.text(1017, 310, "All UI logic in Python", 15, "#b5cede")
    for y, title, lines in [
        (
            366,
            "Fleet catalog",
            ["Interactive topology", "Owner + source inspector", "Dependency exposure"],
        ),
        (
            526,
            "Signal lab",
            ["Run five experiments", "Trace / queue visuals", "Download evidence"],
        ),
        (
            686,
            "Field guide",
            [
                "Architecture + test cases",
                "Technology + tradeoffs",
                "Scaling + extensions",
            ],
        ),
    ]:
        d.text(1017, y, title, 20, "#fff", 700)
        for i, line in enumerate(lines):
            d.text(1017, y + 28 + i * 24, line, 15, "#b5cede")
    d.arrow(945, 286, 995, 286)
    d.arrow(945, 768, 995, 768)
    d.text(48, 909, "SHARED CONTEXT", 12, TEAL, 700)
    d.text(
        205,
        909,
        "Canonical node, service, cluster, and owner identifiers connect the two views.",
        17,
        NAVY,
    )
    d.footer(
        "Inventory models 96 GPU slots. The measured workload is CPU hashing; no GPU performance is claimed."
    )
    d.save("architecture.svg")

    d = Diagram(
        "A value is useful when you can explain it.",
        "Stable identity joins observations. Field policy selects values without hiding disagreements.",
        700,
    )
    d.card(
        48,
        190,
        350,
        140,
        "SERVICE CATALOG",
        "owner = team:inference",
        ["Authoritative ownership, observed at T1"],
        TEAL,
    )
    d.card(
        48,
        355,
        350,
        140,
        "KUBERNETES",
        "owner = team:platform",
        ["Conflicting ownership, observed at T2"],
        PURPLE,
    )
    d.card(
        48,
        520,
        350,
        110,
        "REDFISH",
        "serial = FTL-A11",
        ["Stable physical identity"],
        BLUE,
    )
    for y in [260, 425, 570]:
        d.arrow(398, y, 464, y)
    d.rect(464, 190, 270, 440, NAVY, NAVY)
    d.text(488, 232, "RECONCILIATION", 13, "#80ddd7", 700)
    for i, line in enumerate(
        [
            "1. Validate identity",
            "2. Check batch replay",
            "3. Reject older input",
            "4. Apply field policy",
            "5. Retain provenance",
            "6. Commit atomically",
        ]
    ):
        d.text(488, 287 + i * 51, line, 18, "#e1edf7")
    d.arrow(734, 410, 790, 410)
    d.card(
        790,
        190,
        442,
        185,
        "RESOLVED RECORD",
        "One entity, one chosen owner",
        [
            "owner = team:inference",
            "provenance = service-catalog @ T1",
            "conflict = Kubernetes says team:platform",
        ],
        TEAL,
    )
    d.card(
        790,
        405,
        442,
        225,
        "HISTORY & DATA QUALITY",
        "Absence is a signal",
        [
            "Partial loss → source_absent",
            "All sources absent → unobserved",
            "TTL expired → source_stale",
            "References missing → visible finding",
        ],
        PURPLE,
    )
    d.footer(
        "A newer non-authoritative observation does not silently replace the authoritative owner."
    )
    d.save("reconciliation.svg")

    d = Diagram(
        "Crash the Collector. Keep the evidence.",
        "A controlled restart test against the actual persistent exporter queues.",
        640,
    )
    for x, kicker, title, lines in [
        (
            48,
            "01 / BLOCK",
            "Backend unavailable",
            ["Relay returns 503", "20 traces + 20 log events"],
        ),
        (
            355,
            "02 / PERSIST",
            "Wait for backlog",
            ["Verify accepted signals", "Observe queued batches"],
        ),
        (
            662,
            "03 / CRASH",
            "Abrupt process loss",
            ["SIGKILL owned Collector", "Restart with same WAL"],
        ),
        (
            969,
            "04 / RESTORE",
            "Verify recovery",
            ["Clear injected outage", "Find every unique event"],
        ),
    ]:
        d.card(x, 205, 263, 210, kicker, title, lines, TEAL if x == 969 else BLUE)
    for x in [311, 618, 925]:
        d.arrow(x, 305, x + 44, 305)
    d.rect(48, 465, 1184, 100, NAVY, NAVY)
    d.text(73, 501, "THE GUARANTEE HAS A BOUNDARY", 13, "#80ddd7", 700)
    d.text(
        73,
        535,
        "Only telemetry already in persistent export storage is covered by this test. Disk loss and queue limits still matter.",
        17,
        "#e1edf7",
    )
    d.footer(
        "Records are checked by unique IDs. Replay may duplicate delivery; exactly-once semantics are not claimed."
    )
    d.save("recovery.svg")

    d = Diagram(
        "Scale the evidence, then scale the system.",
        "An extension path with verification gates, not an unmeasured throughput promise.",
        730,
    )
    for y, n, title, lines, col in [
        (
            190,
            "01",
            "Runnable lab",
            [
                "27 entities · one API worker · full projection",
                "Prove identity, ownership, delivery, and recovery",
            ],
            TEAL,
        ),
        (
            315,
            "02",
            "Growing fleet",
            [
                "Incremental reconciliation · bulk upserts · indexed edges",
                "Compare results to the full-rebuild oracle and measure p95",
            ],
            BLUE,
        ),
        (
            440,
            "03",
            "Multiple sites and teams",
            [
                "Partitioned sources · durable jobs · regional Collector gateways",
                "Prove concurrency, isolation, outage capacity, and restore",
            ],
            PURPLE,
        ),
        (
            565,
            "04",
            "Operational platform",
            [
                "OIDC / RBAC · HA storage · migrations · measured SLOs",
                "Exercise failure boundaries before expanding the scope",
            ],
            NAVY,
        ),
    ]:
        d.rect(48, y, 1184, 105)
        d.text(73, y + 61, n, 32, col, 700)
        d.text(153, y + 42, title, 23, NAVY, 700)
        d.text(540, y + 37, lines[0], 17, MUTED)
        d.text(540, y + 69, lines[1], 16, MUTED)
    d.footer(
        "Queue planning: peak batches/second × outage seconds × headroom. Validate bytes, drain rate, and data loss in a load test."
    )
    d.save("scaling.svg")


def build_html():
    chapters = [
        ("overview", "OVERVIEW.md"),
        ("architecture", "ARCHITECTURE.md"),
        ("technologies", "TECHNOLOGIES.md"),
        ("testing", "TESTING.md"),
        ("scaling", "SCALING.md"),
        ("roadmap", "ROADMAP.md"),
        ("runbooks", "RUNBOOKS.md"),
    ]
    sections = []
    nav = []
    for i, (slug, name) in enumerate(chapters, 1):
        content = (ROOT / "docs" / name).read_text()
        title = content.splitlines()[0].removeprefix("# ")
        nav.append(f'<a href="#{slug}"><span>0{i}</span>{escape(title)}</a>')
        rendered = markdown.markdown(
            content, extensions=["tables", "fenced_code", "toc"]
        )
        # Inline SVG makes this file portable; no external images or scripts are needed.
        for svg in ASSETS.glob("*.svg"):
            rendered = re.sub(
                r'<img[^>]*src="assets/' + re.escape(svg.name) + r'"[^>]*/?>',
                lambda _: svg.read_text(),
                rendered,
            )
        for target, file in chapters:
            rendered = rendered.replace(f'href="{file}"', f'href="#{target}"')
        rendered = rendered.replace(
            'href="../evidence/README.md"',
            'href="https://github.com/sivalinb/fleet-telemetry-lab/tree/main/evidence"',
        )
        sections.append(
            f'<section id="{slug}"><p class="chapter">CHAPTER 0{i}</p>{rendered}</section>'
        )
    style = """*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:#f2f6fb;color:#1c3551;font:17px/1.65 system-ui,-apple-system,sans-serif}header{background:#102d4a;color:#fff;padding:76px max(6vw,24px)}header small{color:#80ddd7;letter-spacing:.18em;font-weight:700}header h1{font-size:clamp(46px,7vw,82px);letter-spacing:-.055em;line-height:1.05;margin:22px 0}header p{font-size:21px;max-width:780px;color:#c0d4e6}header a{color:#80ddd7}.layout{display:grid;grid-template-columns:270px minmax(0,1000px);gap:48px;max-width:1420px;padding:48px 32px;margin:auto}nav{position:sticky;top:24px;height:max-content}nav a{display:block;text-decoration:none;border-bottom:1px solid #d4dfeb;padding:12px 0;color:#35516e;font-size:14px}nav span{color:#007f86;margin-right:12px}section{background:#fff;padding:42px;margin-bottom:30px;border:1px solid #dce5ef;border-radius:18px;scroll-margin-top:20px}section>h1{font-size:36px;letter-spacing:-.04em;line-height:1.15;margin-top:4px}h2{font-size:25px;letter-spacing:-.025em;margin-top:36px}.chapter{font-size:12px;color:#007f86;font-weight:700;letter-spacing:.14em}a{color:#195eab}p{margin:16px 0}table{border-collapse:collapse;width:100%;font-size:14px;line-height:1.5;margin:24px 0}th,td{border-bottom:1px solid #dce5ef;padding:12px;text-align:left;vertical-align:top}th{background:#eaf2fa;color:#214b71}tr:nth-child(even){background:#f7f9fc}pre{padding:20px;background:#102d4a;color:#d9edf5;border-radius:12px;overflow:auto;font-size:13px;line-height:1.65}code{font-family:ui-monospace,monospace;font-size:.87em}svg{display:block;width:100%;height:auto;margin:28px 0}footer{padding:40px;text-align:center;color:#5b738d;font-size:14px}@media(max-width:950px){.layout{display:block;padding:20px}nav{position:static;margin-bottom:24px;display:grid;grid-template-columns:1fr 1fr;gap:0 20px}section{padding:24px;overflow-x:auto}table{min-width:560px}}@media print{body{background:#fff;font-size:11pt}header{padding:30px}header h1{font-size:40pt}.layout{display:block;padding:0}nav{display:none}section{break-before:page;border:0;padding:20px}h2,h1{break-after:avoid}tr,pre{break-inside:avoid}a{color:inherit}svg{max-height:680px}footer{display:none}}"""
    page = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Fleet Atlas — Illustrated Field Guide</title><style>'
        + style
        + '</style></head><body><header><small>PYTHON INFRASTRUCTURE LAB / SIVA BABU</small><h1>Know the fleet.<br>Follow the signal.</h1><p>An illustrated guide to source reconciliation, service ownership, observability, and failure recovery — with runnable code and inspectable evidence.</p><a href="https://github.com/sivalinb/fleet-telemetry-lab">Explore the public repository →</a></header><div class="layout"><nav aria-label="Chapters">'
        + "".join(nav)
        + "</nav><main>"
        + "".join(sections)
        + "</main></div><footer>Fleet Atlas · Fictional infrastructure, real telemetry experiments · Generated entirely with Python.</footer></body></html>"
    )
    (ROOT / "docs/field-guide.html").write_text(page)
    (ROOT / "docs/index.html").write_text(
        '<!doctype html><html><head><meta http-equiv="refresh" content="0;url=field-guide.html"><title>Fleet Atlas guide</title></head><body><a href="field-guide.html">Read the field guide</a></body></html>'
    )
    print("Generated four SVG diagrams and docs/field-guide.html")


if __name__ == "__main__":
    diagrams()
    build_html()
