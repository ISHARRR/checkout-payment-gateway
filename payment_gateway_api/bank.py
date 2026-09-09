"""Translate our validated request into the acquiring bank's HTTP contract."""

import os

import httpx

from payment_gateway_api.models import PaymentRequest


class BankError(Exception):
    """A technical failure, carrying a safe message for the merchant."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code


def process_payment(payment: PaymentRequest) -> bool:
    """Make one bank request and return its explicit authorization decision."""
    payload = {
        "card_number": payment.card_number,
        # The bank accepts one expiry string; our public API accepts two integers.
        "expiry_date": f"{payment.expiry_month:02d}/{payment.expiry_year:04d}",
        "currency": payment.currency,
        "amount": payment.amount,
        "cvv": payment.cvv,
    }
    try:
        # A bounded timeout prevents waiting indefinitely for an unresponsive bank.
        # Do not retry: a lost response does not prove the bank declined the payment.
        response = httpx.post(
            os.getenv("BANK_URL", "http://localhost:8080/payments"),
            json=payload,
            timeout=5.0,
        )
    except httpx.RequestError:
        # Do not forward the exception or request: they can contain card details.
        raise BankError(503, "Bank unavailable; payment outcome could not be confirmed") from None

    if response.status_code == 503:
        raise BankError(503, "Bank unavailable; payment outcome could not be confirmed")
    if response.status_code != 200:
        raise BankError(502, "Bank returned an unexpected response")

    try:
        result = response.json()
    except ValueError:
        raise BankError(502, "Bank returned an invalid response") from None

    # Only an actual JSON boolean is a decision. Missing values, "false" or 0
    # must never be silently converted into a declined or authorized payment.
    if not isinstance(result, dict) or type(result.get("authorized")) is not bool:
        raise BankError(502, "Bank returned an invalid response")
    return result["authorized"]
