"""A small in-memory repository, as permitted by the assessment."""

from payment_gateway_api.models import Payment


class PaymentRepository:
    """Each application instance owns its records; restart clears them."""

    def __init__(self) -> None:
        self._payments: dict[str, Payment] = {}

    def save(self, payment: Payment) -> None:
        """Store only the safe Payment model, never the original request."""
        self._payments[payment.id] = payment

    def get(self, payment_id: str) -> Payment | None:
        """A missing ID returns None so the endpoint can choose the HTTP response."""
        return self._payments.get(payment_id)
