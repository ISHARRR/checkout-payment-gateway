from datetime import date
from unittest.mock import Mock

import httpx
import pytest
from fastapi.testclient import TestClient

from payment_gateway_api import bank, models
from payment_gateway_api.app import create_app


@pytest.fixture
def valid_payment():
    return {
        "card_number": "4242424242424241",
        "expiry_month": 10,
        "expiry_year": 2026,
        "currency": "GBP",
        "amount": 100,
        "cvv": "987",
    }


@pytest.fixture
def application(monkeypatch):
    # A fixed clock makes expiry tests independent of when someone runs them.
    monkeypatch.setattr(models, "current_date", lambda: date(2026, 9, 8))
    return create_app()


@pytest.fixture
def client(application):
    with TestClient(application) as test_client:
        yield test_client


@pytest.fixture
def bank_post(monkeypatch):
    # Replace only the network boundary: validation and our bank adapter run normally.
    monkeypatch.delenv("BANK_URL", raising=False)
    response = httpx.Response(
        200,
        json={"authorized": True, "authorization_code": "bank-reference"},
        request=httpx.Request("POST", "http://localhost:8080/payments"),
    )
    post = Mock(return_value=response)
    monkeypatch.setattr(bank.httpx, "post", post)
    return post
