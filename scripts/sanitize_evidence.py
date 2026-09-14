"""Remove local machine metadata from checked-in verification records."""

import json
from pathlib import Path
from xml.etree import ElementTree

from fleetlab.reports import public_result

ROOT = Path(__file__).resolve().parents[1]


def main():
    for path in (ROOT / "evidence").rglob("*.json"):
        path.write_text(
            json.dumps(
                public_result(json.loads(path.read_text())), separators=(",", ":")
            )
            + "\n"
        )
    path = ROOT / "evidence/unit-tests.xml"
    if path.exists():
        tree = ElementTree.parse(path)
        for element in tree.iter():
            element.attrib.pop("hostname", None)
        tree.write(path, encoding="unicode", xml_declaration=True)


if __name__ == "__main__":
    main()
