"""Validate incoming requests and define the safe payment record we return."""

from datetime import date, datetime, timezone
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


def current_date() -> date:
    """Use one timezone; tests replace this small function with a fixed date."""
    return datetime.now(timezone.utc).date()


class PaymentRequest(BaseModel):
    """Only valid requests reach the endpoint and therefore the bank."""

    # Strict types prevent True, 10.0 and "10" from becoming integer amounts.
    # Unknown fields usually indicate a typo, so reject them explicitly.
    model_config = ConfigDict(strict=True, extra="forbid", hide_input_in_errors=True)

    # Strings preserve leading zeroes. [0-9] deliberately allows ASCII digits only.
    # repr=False prevents these fields appearing in a printed model representation.
    card_number: str = Field(min_length=14, max_length=19, pattern=r"^[0-9]+$", repr=False)
    expiry_month: int = Field(ge=1, le=12)
    expiry_year: int = Field(ge=1, le=9999)
    currency: Literal["GBP", "USD", "EUR"]
    # The brief specifies an integer but no minimum; retain that exact contract.
    amount: int
    cvv: str = Field(min_length=3, max_length=4, pattern=r"^[0-9]+$", repr=False)

    @model_validator(mode="after")
    def validate_expiry(self) -> Self:
        """Validate the pair so a later month in the current year is accepted."""
        today = current_date()
        # Tuple comparison checks the year first, then the month if years match.
        # Our documented interpretation of "future" excludes the current month.
        if (self.expiry_year, self.expiry_month) <= (today.year, today.month):
            raise ValueError("Expiry month and year must be in the future")
        return self


class Payment(BaseModel):
    """The stored record is also the public response: it has no full card or CVV."""

    # Immutable records can be returned by the memory repository without copying.
    model_config = ConfigDict(frozen=True)

    id: str
    status: Literal["Authorized", "Declined"]
    card_number_last_four: str
    expiry_month: int
    expiry_year: int
    currency: Literal["GBP", "USD", "EUR"]
    amount: int
