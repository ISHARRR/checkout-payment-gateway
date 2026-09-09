"""Two payment endpoints, with validation before any acquiring bank call."""

from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from payment_gateway_api import bank
from payment_gateway_api.models import Payment, PaymentRequest
from payment_gateway_api.repository import PaymentRepository


def create_app() -> FastAPI:
    """Give each app its own repository, keeping test cases independent."""
    app = FastAPI(title="Payment Gateway", version="1.0.0")
    repository = PaymentRepository()
    app.state.repository = repository

    @app.exception_handler(RequestValidationError)
    async def reject_invalid_request(request: Request, exc: RequestValidationError) -> JSONResponse:
        """Return useful errors without echoing submitted values or raw request bodies."""
        errors = []
        for error in exc.errors():
            location = error["loc"]
            field = location[1] if len(location) > 1 else "request"
            # Even an unexpected field NAME can contain sensitive user input.
            if field not in PaymentRequest.model_fields:
                field = "request"
            errors.append({"field": field, "message": error["msg"]})
        return JSONResponse(status_code=400, content={"status": "Rejected", "errors": errors})

    @app.get("/")
    def ping() -> dict[str, str]:
        """Keep the starter's simple health endpoint."""
        return {"app": "payment-gateway-api"}

    @app.post(
        "/payments",
        response_model=Payment,
        status_code=201,
        responses={
            400: {"description": "Rejected request; the bank was not called"},
            # A documented 4XX response suppresses FastAPI's default 422 entry.
            "4XX": {"description": "Invalid request"},
            502: {"description": "Invalid or unexpected bank response"},
            503: {"description": "Bank unavailable; outcome unconfirmed"},
        },
    )
    def create_payment(payment: PaymentRequest, response: Response) -> Payment:
        """Validate -> call bank -> construct safe record -> save -> return."""
        # FastAPI validates PaymentRequest before entering this function.
        # This synchronous route matches the synchronous HTTP bank call.
        try:
            authorized = bank.process_payment(payment)
        except bank.BankError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from None

        record = Payment(
            id=str(uuid4()),
            status="Authorized" if authorized else "Declined",
            card_number_last_four=payment.card_number[-4:],
            expiry_month=payment.expiry_month,
            expiry_year=payment.expiry_year,
            currency=payment.currency,
            amount=payment.amount,
        )
        # Both bank decisions are valid records. Technical failures never reach here.
        repository.save(record)
        response.headers["Location"] = f"/payments/{record.id}"
        return record

    @app.get(
        "/payments/{payment_id}",
        response_model=Payment,
        responses={404: {"description": "Payment not found"}},
    )
    def get_payment(payment_id: str) -> Payment:
        """Look up the saved result; retrieving a payment never calls the bank."""
        payment = repository.get(payment_id)
        if payment is None:
            raise HTTPException(status_code=404, detail="Payment not found")
        return payment

    return app


# Uvicorn imports this object when starting the application.
app = create_app()
