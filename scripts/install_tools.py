"""Install pinned official observability binaries into the project, with SHA-256 checks."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import hashlib
import json
import platform
import shutil
import tarfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / ".runtime" / "bin"
VERSIONS = {
    "collector": ("open-telemetry/opentelemetry-collector-releases", "0.160.0"),
    "prometheus": ("prometheus/prometheus", "3.14.0"),
    "loki": ("grafana/loki", "3.7.7"),
    "jaeger": ("jaegertracing/jaeger", "2.20.0"),
}


def install(name):
    system = platform.system().lower()
    arch = {"aarch64": "arm64", "arm64": "arm64", "x86_64": "amd64"}.get(
        platform.machine()
    )
    if system not in {"darwin", "linux"} or not arch:
        raise SystemExit(
            "Native quickstart supports macOS/Linux arm64/amd64. Use Docker on other platforms."
        )
    repo, version = VERSIONS[name]
    asset_name = {
        "collector": f"otelcol-contrib_{version}_{system}_{arch}.tar.gz",
        "prometheus": f"prometheus-{version}.{system}-{arch}.tar.gz",
        "loki": f"loki-{system}-{arch}.zip",
        "jaeger": f"jaeger-{version}-{system}-{arch}.tar.gz",
    }[name]
    TOOLS.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(
        f"https://api.github.com/repos/{repo}/releases/tags/v{version}", timeout=30
    ) as response:
        release = json.load(response)
    asset = next(a for a in release["assets"] if a["name"] == asset_name)
    expected = (asset.get("digest") or "").removeprefix("sha256:")
    if len(expected) != 64:
        raise RuntimeError(
            f"Official release has no SHA-256 digest for {asset_name}; refusing an unverified download"
        )
    archive = ROOT / ".runtime" / asset_name
    if (
        not archive.exists()
        or hashlib.sha256(archive.read_bytes()).hexdigest() != expected
    ):
        print(f"Downloading {name} {version}", flush=True)
        urllib.request.urlretrieve(asset["browser_download_url"], archive)
    if hashlib.sha256(archive.read_bytes()).hexdigest() != expected:
        raise RuntimeError(f"Checksum mismatch: {asset_name}")
    target_name = {
        "collector": "otelcol-contrib",
        "prometheus": "prometheus",
        "loki": f"loki-{system}-{arch}",
        "jaeger": "jaeger",
    }[name]
    target = TOOLS / name
    if archive.suffix == ".zip":
        with zipfile.ZipFile(archive) as z:
            member = next(m for m in z.namelist() if Path(m).name == target_name)
            target.write_bytes(z.read(member))
    else:
        with tarfile.open(archive) as t:
            member = next(
                m
                for m in t.getmembers()
                if Path(m.name).name == target_name and m.isfile()
            )
            with t.extractfile(member) as source, target.open("wb") as output:
                shutil.copyfileobj(source, output)
    target.chmod(0o755)
    print(f"Verified {name} {version}", flush=True)
    return {
        "name": name,
        "version": version,
        "asset": asset_name,
        "sha256": expected,
        "url": asset["browser_download_url"],
    }


if __name__ == "__main__":
    with ThreadPoolExecutor(max_workers=4) as pool:
        evidence = list(pool.map(install, VERSIONS))
    (ROOT / ".runtime" / "tools-lock.json").write_text(
        json.dumps(evidence, indent=2) + "\n"
    )
