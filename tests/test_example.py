from fastapi.testclient import TestClient

from payment_gateway_api.app import app


def test_example():
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {"app": "payment-gateway-api"}
