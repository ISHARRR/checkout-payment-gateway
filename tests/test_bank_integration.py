"""Opt-in tests against the supplied simulator: RUN_BANK_INTEGRATION=1 pytest."""

import os
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from payment_gateway_api.app import create_app

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_BANK_INTEGRATION") != "1",
        reason="Start the bank simulator and set RUN_BANK_INTEGRATION=1 to run integration tests",
    ),
]


@pytest.mark.parametrize(
    ("last_digit", "expected_http_status", "expected_payment_status"),
    [("1", 201, "Authorized"), ("2", 201, "Declined"), ("0", 503, None)],
)
def test_supplied_bank_simulator(last_digit, expected_http_status, expected_payment_status):
    application = create_app()
    # Next year stays in the future without needing to edit this example over time.
    payment = {
        "card_number": "424242424242424" + last_digit,
        "expiry_month": 1,
        "expiry_year": datetime.now(timezone.utc).year + 1,
        "currency": "GBP",
        "amount": 100,
        "cvv": "987",
    }

    with TestClient(application) as client:
        response = client.post("/payments", json=payment)

        assert response.status_code == expected_http_status
        if expected_payment_status is not None:
            assert response.json()["status"] == expected_payment_status
            payment_id = response.json()["id"]
            retrieved = client.get(f"/payments/{payment_id}")
            assert retrieved.status_code == 200
            assert retrieved.json() == response.json()
        else:
            assert application.state.repository._payments == {}
