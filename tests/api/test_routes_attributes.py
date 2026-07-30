import pytest


@pytest.mark.integration
def test_attributes_endpoint_404_when_manuscript_absent(api_client):
    """404 para un manuscrito inexistente.

    Marcado `integration` porque el endpoint consulta el grafo para decidir el
    404: sin Neo4j la ruta devuelve 500, no 404. Usa la fixture `api_client`
    para no cerrar el driver compartido entre tests (ver conftest).
    """
    r = api_client.get("/manuscripts/does-not-exist/attributes")
    assert r.status_code == 404


def test_router_is_registered():
    from backend.api.app import app
    paths = {route.path for route in app.routes}
    assert "/manuscripts/{manuscript_id}/attributes" in paths
