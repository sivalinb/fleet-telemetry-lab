"""Drive Streamlit itself with a real FastAPI TestClient backing its HTTP calls."""

from pathlib import Path
from fastapi.testclient import TestClient
import httpx
from streamlit.testing.v1 import AppTest
from fleetlab.api import create_app

ROOT = Path(__file__).resolve().parents[2]


def test_catalog_scenario_and_field_guide(tmp_path, monkeypatch):
    app = create_app("sqlite:///" + str(tmp_path / "ui.db"))
    with TestClient(app) as api:

        class Bridge:
            def __init__(self, **kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def get(self, url):
                return api.get(url.removeprefix("http://127.0.0.1:8001"))

            def post(self, url, json):
                return api.post(url.removeprefix("http://127.0.0.1:8001"), json=json)

        monkeypatch.setattr(httpx, "Client", Bridge)
        monkeypatch.delenv("LAB_API_TOKEN", raising=False)
        monkeypatch.delenv("FLEET_API_URL", raising=False)
        at = AppTest.from_file(str(ROOT / "streamlit_app.py"), default_timeout=15).run()
        assert not at.exception
        assert at.metric[0].value == "27" and at.metric[1].value == "96"
        at.selectbox[1].select("Ownership conflict").run()
        at.button[0].click().run()
        assert not at.exception
        assert any(
            i["code"] == "owner_conflict"
            for e in api.get("/api/catalog").json()["entities"]
            for i in e["issues"]
        )
        at.session_state["workspace"] = "Field guide"
        at.run()
        assert not at.exception
        assert any(t.value == "The field guide" for t in at.title)
        at.selectbox[0].select("Architecture").run()
        assert not at.exception
        assert any("Runtime paths" in t.value for t in at.markdown)


def test_api_unavailable_is_visible(monkeypatch):
    original = httpx.Client

    def fail(request):
        raise httpx.ConnectError("offline", request=request)

    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kw: original(transport=httpx.MockTransport(fail), **kw),
    )
    at = AppTest.from_file(str(ROOT / "streamlit_app.py"), default_timeout=15).run()
    assert not at.exception
    assert "catalog API is unavailable" in at.error[0].value
