"""Generate portable technical documentation and an HTML architecture overview."""

import json
import re
import tomllib
from html import escape
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
SECTIONS = [
    "OVERVIEW",
    "ARCHITECTURE",
    "TECHNOLOGIES",
    "TESTING",
    "SCALING",
    "EXTENSIONS",
    "RUNBOOKS",
]
STYLE = """
*{box-sizing:border-box}body{margin:0;color:#17354f;background:#f7f9fb;font:18px/1.6 Arial,sans-serif}
a{color:#007b80}h1,h2,h3{line-height:1.12;letter-spacing:-.04em}h1{font-size:46px}h2{font-size:36px}
main.guide{max-width:1100px;margin:auto;padding:52px 40px}article{padding:32px 0;border-bottom:1px solid #d8e4eb}
table{border-collapse:collapse;width:100%;font-size:16px}td,th{padding:12px;text-align:left;border-bottom:1px solid #d7e3eb}
svg{max-width:100%;height:auto}pre{white-space:pre-wrap;background:#edf2f6;padding:18px;border-radius:10px;font-size:14px}code{font-size:.85em}
.slide{display:none;min-height:100vh;padding:8vh 7vw 84px;position:relative;background:#f7f9fb}
.slide:target{display:flex;flex-direction:column}body:not(:has(.slide:target)) .slide:first-child{display:flex;flex-direction:column}
.slide h1{font-size:clamp(34px,4.5vw,64px);max-width:1060px;margin:14px 0 30px}
.slide .body{font-size:clamp(19px,2vw,28px);max-width:1080px}.slide .label{font-size:12px;font-weight:bold;letter-spacing:.16em;text-transform:uppercase;color:#00828a}
.slide:first-child,.slide:last-child{background:#102d4a;color:white}.slide:first-child .label,.slide:last-child .label{color:#80dcd7}
.slide:first-child a,.slide:last-child a{color:#a5eae4}.slide:first-child h1{margin-top:8vh;font-size:clamp(44px,6vw,86px)}
.slide footer{position:absolute;bottom:25px;left:7vw;right:7vw;display:flex;gap:24px;align-items:center;font-size:14px}.slide footer .author{margin-right:auto}
.flow{display:flex;align-items:stretch;gap:14px;margin:24px 0;flex-wrap:wrap}.box{border:1px solid #cddfe7;background:white;padding:22px;border-radius:12px;flex:1;min-width:190px;font-size:20px}.box strong{display:block;margin-bottom:12px;color:#007b80}.box small{font-size:16px;line-height:1.45;display:block}
@media(max-width:700px){.slide{padding:35px 25px 90px}.slide footer{left:25px;right:25px;gap:12px;font-size:12px}.slide h1{font-size:36px}.slide .body{font-size:21px}.slide footer .author{max-width:125px}.box{min-width:140px}main.guide{padding:25px}}
@media print{@page{size:landscape;margin:0}.slide,.slide:target,body:not(:has(.slide:target)) .slide:first-child{display:block;min-height:100vh;break-after:page}.slide footer{display:none}}
"""


def render(text):
    result = markdown.markdown(text, extensions=["tables", "fenced_code"])

    def inline(match):
        path = (DOCS / match.group(1)).resolve()
        if not path.is_relative_to(DOCS.resolve()) or path.suffix != ".svg":
            raise ValueError("Only local SVG documentation assets are supported")
        return path.read_text()

    return re.sub(r'<img alt="[^"]*" src="([^"]+)"\s*/?>', inline, result)


def page(title, body):
    return f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{escape(title)}</title><style>{STYLE}</style></head><body>{body}</body></html>'


def main():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["name"]
    title = (
        "Telemetry Reliability Lab"
        if project == "fleet-telemetry-lab"
        else "Fleet Infrastructure Catalog"
    )
    guide = '<main class="guide"><h1>' + title + "</h1>"
    for section in SECTIONS:
        guide += f'<article id="{section.lower()}">{render((DOCS / (section + ".md")).read_text())}</article>'
    guide += "</main>"
    (DOCS / "field-guide.html").write_text(page(title + " — Technical Guide", guide))
    (DOCS / "index.html").write_text(page(title + " — Technical Guide", guide))
    slides = json.loads((DOCS / "keynote.json").read_text())
    body = '<main aria-label="Technical overview">'
    for index, slide in enumerate(slides, 1):
        previous = f'<a href="#s{index - 1:02}">Back</a>' if index > 1 else ""
        following = (
            f'<a href="#s{index + 1:02}">Next</a>'
            if index < len(slides)
            else '<a href="#s01">Start</a>'
        )
        body += f'<section class="slide" id="s{index:02}" aria-label="Slide {index}: {escape(slide["title"])}"><div class="label">{escape(slide["label"])}</div><h1>{escape(slide["title"])}</h1><div class="body">{render(slide["body"])}</div><footer><a class="author" href="https://github.com/sivalinb/{project}">Siva Babu · {title}</a>{previous}<span>{index:02} / {len(slides):02}</span>{following}</footer></section>'
    body += "</main>"
    (DOCS / "keynote.html").write_text(page(title + " — Technical Overview", body))
    print(f"Generated {title}: technical guide and {len(slides)}-section overview")


if __name__ == "__main__":
    main()
