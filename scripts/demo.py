"""Run a standalone demo, or use --live for the API and supplied bank simulator."""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import httpx

API_URL = "http://127.0.0.1:8000"


def main(argv: list[str] | None = None) -> None:
    """Default to a standalone demo that can run directly from PyCharm."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live", action="store_true", help=f"Use the running API at {API_URL} and its bank"
    )
    args = parser.parse_args(argv)
    if not args.live:
        run_standalone()
        return

    print(f"Live demo: using {API_URL}")
    try:
        with httpx.Client(base_url=API_URL, timeout=10) as client:
            run_demo(client)
    except httpx.ConnectError:
        raise SystemExit(
            f"Cannot connect to the payment API at {API_URL}.\n"
            f"From {Path(__file__).resolve().parents[1]}, run:\n"
            "  docker compose up -d\n"
            "  poetry run python main.py\n"
            "Leave the API running, then rerun scripts/demo.py --live.\n"
            "For a standalone demo without services, run scripts/demo.py without --live."
        ) from None


def run_standalone() -> None:
    """Exercise the real API in process, replacing only the bank HTTP call."""
    # Direct script execution puts scripts/ on sys.path, regardless of working directory.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from fastapi.testclient import TestClient

    from payment_gateway_api.app import create_app

    def simulated_bank(url, *, json, timeout):
        final_digit = json["card_number"][-1]
        if final_digit == "0":
            return httpx.Response(503, json={})
        return httpx.Response(200, json={"authorized": int(final_digit) % 2 == 1})

    print("Standalone demo: in-process API with simulated bank responses (no services needed).")
    with (
        patch("payment_gateway_api.bank.httpx.post", side_effect=simulated_bank),
        TestClient(create_app()) as client,
    ):
        run_demo(client)


def run_demo(client: httpx.Client) -> None:
    """Demonstrate every required outcome without printing submitted card details."""
    payment = {
        "card_number": "2222405343248877",
        "expiry_month": 12,
        "expiry_year": datetime.now(timezone.utc).year + 1,
        "currency": "GBP",
        "amount": 1050,
        "cvv": "123",
    }
    for label, final_digit in [
        ("Authorized", "7"),
        ("Declined", "8"),
        ("Bank unavailable", "0"),
    ]:
        payment["card_number"] = "222240534324887" + final_digit
        response = client.post("/payments", json=payment)
        print(f"{label}: HTTP {response.status_code} {response.json()}")
        if response.status_code == 503 and label != "Bank unavailable":
            raise SystemExit(
                "The API is running, but the bank is unavailable.\n"
                "Start the supplied simulator with 'docker compose up -d' "
                "from the project directory, then rerun the demo.\n"
                "If BANK_URL is set for the API, check that endpoint too."
            )
        if response.status_code == 201:
            retrieved = client.get(response.headers["Location"])
            print(f"Retrieved: HTTP {retrieved.status_code} {retrieved.json()}")

    payment["cvv"] = "invalid"
    response = client.post("/payments", json=payment)
    print(f"Rejected before bank call: HTTP {response.status_code} {response.json()}")


if __name__ == "__main__":
    main()
