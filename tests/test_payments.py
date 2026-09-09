from copy import deepcopy
from datetime import date
from uuid import UUID

import httpx
import pytest
from fastapi.testclient import TestClient

from payment_gateway_api import models
from payment_gateway_api.app import create_app
from payment_gateway_api.models import PaymentRequest

RESPONSE_FIELDS = {
    "id",
    "status",
    "card_number_last_four",
    "expiry_month",
    "expiry_year",
    "currency",
    "amount",
}


def assert_rejected(response, application, bank_post):
    """Every invalid request must stop before contacting the bank or saving anything."""
    assert response.status_code == 400
    body = response.json()
    assert body["status"] == "Rejected"
    assert body["errors"]
    for error in body["errors"]:
        assert set(error) == {"field", "message"}
        assert isinstance(error["field"], str)
        assert isinstance(error["message"], str)
        assert error["message"]
    bank_post.assert_not_called()
    assert application.state.repository._payments == {}


@pytest.mark.parametrize(
    ("authorized", "expected_status"), [(True, "Authorized"), (False, "Declined")]
)
def test_process_and_retrieve_payment(
    client, application, bank_post, valid_payment, authorized, expected_status
):
    bank_post.return_value = httpx.Response(200, json={"authorized": authorized})
    original_request = deepcopy(valid_payment)

    response = client.post("/payments", json=valid_payment)

    assert response.status_code == 201
    payment = response.json()
    assert UUID(payment["id"]).version == 4
    assert payment == {
        "id": payment["id"],
        "status": expected_status,
        "card_number_last_four": "4241",
        "expiry_month": 10,
        "expiry_year": 2026,
        "currency": "GBP",
        "amount": 100,
    }
    # Only the bank needs the full card number and CVV. The gateway keeps safe fields.
    stored = application.state.repository.get(payment["id"])
    assert set(stored.model_dump()) == RESPONSE_FIELDS
    assert valid_payment["card_number"] not in repr(stored)
    assert valid_payment["cvv"] not in repr(stored)

    retrieved = client.get(f"/payments/{payment['id']}")
    assert retrieved.status_code == 200
    assert retrieved.json() == payment
    # Looking up a payment must not submit it to the bank again.
    bank_post.assert_called_once_with(
        "http://localhost:8080/payments",
        json={
            "card_number": "4242424242424241",
            "expiry_date": "10/2026",
            "currency": "GBP",
            "amount": 100,
            "cvv": "987",
        },
        timeout=5.0,
    )
    assert valid_payment == original_request


def test_payment_ids_are_unique(client, bank_post, valid_payment):
    first = client.post("/payments", json=valid_payment).json()
    second = client.post("/payments", json={**valid_payment, "amount": 200}).json()

    assert first["id"] != second["id"]
    assert client.get(f"/payments/{first['id']}").json()["amount"] == 100
    assert client.get(f"/payments/{second['id']}").json()["amount"] == 200


@pytest.mark.parametrize("payment_id", ["unknown", "00000000-0000-0000-0000-000000000000"])
def test_unknown_payment_returns_not_found(client, bank_post, payment_id):
    response = client.get(f"/payments/{payment_id}")

    assert response.status_code == 404
    assert response.json() == {"detail": "Payment not found"}
    bank_post.assert_not_called()


def test_fresh_app_starts_with_empty_storage(client, bank_post, valid_payment):
    payment = client.post("/payments", json=valid_payment).json()

    with TestClient(create_app()) as other_client:
        assert other_client.get(f"/payments/{payment['id']}").status_code == 404


@pytest.mark.parametrize(
    "field", ["card_number", "expiry_month", "expiry_year", "currency", "amount", "cvv"]
)
@pytest.mark.parametrize("missing", [True, False], ids=["missing", "null"])
def test_all_fields_are_required(client, application, bank_post, valid_payment, field, missing):
    if missing:
        del valid_payment[field]
    else:
        valid_payment[field] = None

    assert_rejected(client.post("/payments", json=valid_payment), application, bank_post)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("card_number", "1" * 13),
        ("card_number", "1" * 20),
        ("card_number", "424242424242424x"),
        ("card_number", "4242 424242424241"),
        ("card_number", "4242424242424241\n"),
        ("card_number", "４" * 16),
        ("card_number", "٤" * 16),
        ("card_number", 4242424242424241),
        ("card_number", True),
        ("card_number", ""),
        ("cvv", "12"),
        ("cvv", "12345"),
        ("cvv", "12x"),
        ("cvv", "1 2"),
        ("cvv", "123\n"),
        ("cvv", "１２３"),
        ("cvv", "١٢٣"),
        ("cvv", 123),
        ("cvv", True),
        ("cvv", ""),
        ("expiry_month", 0),
        ("expiry_month", 13),
        ("expiry_month", "10"),
        ("expiry_month", 10.0),
        ("expiry_month", True),
        ("expiry_year", 0),
        ("expiry_year", 10000),
        ("expiry_year", "2027"),
        ("expiry_year", 2027.0),
        ("expiry_year", True),
        ("currency", "JPY"),
        ("currency", "gbp"),
        ("currency", "GBP "),
        ("currency", ""),
        ("currency", 123),
        ("amount", 100.0),
        ("amount", 1.5),
        ("amount", "100"),
        ("amount", True),
        ("amount", False),
    ],
)
def test_invalid_field_is_rejected(client, application, bank_post, valid_payment, field, value):
    valid_payment[field] = value

    assert_rejected(client.post("/payments", json=valid_payment), application, bank_post)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        # Check every allowed card length, including preservation of leading zeroes.
        *[("card_number", "0" * (length - 1) + "1") for length in range(14, 20)],
        ("cvv", "012"),
        ("cvv", "0012"),
        ("currency", "GBP"),
        ("currency", "USD"),
        ("currency", "EUR"),
        ("amount", 0),
        ("amount", -1),
        ("expiry_month", 12),
        ("expiry_year", 9999),
    ],
)
def test_valid_boundaries_are_accepted(client, bank_post, valid_payment, field, value):
    valid_payment[field] = value

    response = client.post("/payments", json=valid_payment)

    assert response.status_code == 201
    bank_post.assert_called_once()
    if field in {"card_number", "cvv"}:
        assert bank_post.call_args.kwargs["json"][field] == value
    if field == "card_number":
        assert response.json()["card_number_last_four"] == value[-4:]


@pytest.mark.parametrize(
    ("today", "month", "year", "accepted"),
    [
        (date(2026, 9, 8), 8, 2026, False),
        (date(2026, 9, 8), 9, 2026, False),
        (date(2026, 9, 8), 10, 2026, True),
        (date(2026, 9, 8), 12, 2025, False),
        (date(2026, 9, 8), 1, 2027, True),
        (date(2026, 12, 31), 12, 2026, False),
        (date(2026, 12, 31), 1, 2027, True),
        (date(2027, 1, 1), 1, 2027, False),
        (date(2027, 1, 1), 2, 2027, True),
    ],
)
def test_expiry_compares_month_and_year_together(
    client, application, bank_post, valid_payment, monkeypatch, today, month, year, accepted
):
    monkeypatch.setattr(models, "current_date", lambda: today)
    valid_payment.update(expiry_month=month, expiry_year=year)

    response = client.post("/payments", json=valid_payment)

    if accepted:
        assert response.status_code == 201
        assert bank_post.call_args.kwargs["json"]["expiry_date"] == f"{month:02d}/{year:04d}"
    else:
        assert_rejected(response, application, bank_post)


def test_extra_fields_are_rejected_without_echoing_sensitive_input(
    client, application, bank_post, valid_payment, caplog
):
    # Even an unknown JSON field name can contain a card number; do not echo it.
    valid_payment[valid_payment["card_number"]] = valid_payment["cvv"]

    response = client.post("/payments", json=valid_payment)

    assert_rejected(response, application, bank_post)
    for secret in (valid_payment["card_number"], valid_payment["cvv"]):
        assert secret not in response.text
        assert secret not in caplog.text


@pytest.mark.parametrize(
    "invalid_fields", [{"cvv": "98765"}, {"expiry_year": 2025}], ids=["field", "whole-model"]
)
def test_invalid_values_are_not_echoed_in_errors(
    client, application, bank_post, valid_payment, caplog, invalid_fields
):
    # Check field errors and whole-model expiry errors separately; either can expose input.
    valid_payment.update(invalid_fields)

    response = client.post("/payments", json=valid_payment)

    assert_rejected(response, application, bank_post)
    for secret in (valid_payment["card_number"], valid_payment["cvv"]):
        assert secret not in response.text
        assert secret not in caplog.text


@pytest.mark.parametrize("body", ["{", "[]", '"4242424242424241"', "null"])
def test_malformed_or_non_object_body_is_rejected(client, application, bank_post, body):
    response = client.post("/payments", content=body, headers={"Content-Type": "application/json"})

    assert_rejected(response, application, bank_post)
    assert "4242424242424241" not in response.text


def test_request_repr_hides_card_number_and_cvv(application, valid_payment):
    payment = PaymentRequest(**valid_payment)

    assert valid_payment["card_number"] not in repr(payment)
    assert valid_payment["cvv"] not in repr(payment)


def test_success_does_not_log_card_number_or_cvv(client, bank_post, valid_payment, caplog):
    response = client.post("/payments", json=valid_payment)

    assert response.status_code == 201
    for secret in (valid_payment["card_number"], valid_payment["cvv"]):
        assert secret not in response.text
        assert secret not in caplog.text


def test_bank_url_is_configurable(client, bank_post, valid_payment, monkeypatch):
    monkeypatch.setenv("BANK_URL", "http://test-bank:9090/payments")

    assert client.post("/payments", json=valid_payment).status_code == 201
    assert bank_post.call_args.args == ("http://test-bank:9090/payments",)


@pytest.mark.parametrize(
    ("upstream_status", "expected_status"),
    [(503, 503), (400, 502), (500, 502), (201, 502), (302, 502)],
)
def test_unexpected_bank_status_is_a_technical_error(
    client, application, bank_post, valid_payment, upstream_status, expected_status
):
    bank_post.return_value = httpx.Response(
        upstream_status,
        json={"authorized": True, "error": valid_payment["card_number"]},
        request=httpx.Request("POST", "http://localhost:8080/payments"),
    )

    response = client.post("/payments", json=valid_payment)

    assert response.status_code == expected_status
    assert isinstance(response.json()["detail"], str)
    assert valid_payment["card_number"] not in response.text
    bank_post.assert_called_once()
    assert application.state.repository._payments == {}


@pytest.mark.parametrize("error_type", [httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout])
def test_network_failure_is_not_retried_or_recorded(
    client, application, bank_post, valid_payment, caplog, error_type
):
    bank_post.side_effect = error_type(f"request failed: {valid_payment['card_number']}")

    response = client.post("/payments", json=valid_payment)

    assert response.status_code == 503
    assert isinstance(response.json()["detail"], str)
    assert valid_payment["card_number"] not in response.text
    assert valid_payment["card_number"] not in caplog.text
    # A timeout might mean the bank processed a payment; automatically retrying is unsafe.
    bank_post.assert_called_once()
    assert application.state.repository._payments == {}


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"authorized": None},
        {"authorized": "true"},
        {"authorized": "false"},
        {"authorized": 0},
        {"authorized": 1},
        [],
        [True],
        None,
        True,
    ],
)
def test_malformed_bank_response_is_not_a_payment_result(
    client, application, bank_post, valid_payment, body
):
    bank_post.return_value = httpx.Response(200, json=body)

    response = client.post("/payments", json=valid_payment)

    assert response.status_code == 502
    assert isinstance(response.json()["detail"], str)
    bank_post.assert_called_once()
    assert application.state.repository._payments == {}


def test_non_json_bank_response_is_a_safe_technical_error(
    client, application, bank_post, valid_payment
):
    bank_post.return_value = httpx.Response(200, text=valid_payment["card_number"] + " not JSON")

    response = client.post("/payments", json=valid_payment)

    assert response.status_code == 502
    assert valid_payment["card_number"] not in response.text
    assert application.state.repository._payments == {}
