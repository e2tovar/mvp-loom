import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_attributes_endpoint_404_when_manuscript_absent(monkeypatch):
    from backend.api.app import app
    client = TestClient(app)
    r = client.get("/manuscripts/does-not-exist/attributes")
    assert r.status_code == 404


def test_router_is_registered():
    from backend.api.app import app
    paths = {route.path for route in app.routes}
    assert "/manuscripts/{manuscript_id}/attributes" in paths
