# Payment Gateway

A small Python solution to the [Checkout.com engineering assessment](https://github.com/cko-recruitment/),
built from the [official Python starter](https://github.com/cko-recruitment/payment-gateway-challenge-python).

The API validates a payment, asks the supplied bank simulator for a decision, stores the result
in memory and lets the merchant retrieve it. Authorized and declined payments are both saved.
Rejected requests never reach the bank.

## Run

Prerequisites: **Python 3.12**, **Poetry 2** and **Docker with Compose** for the simulator.
Run these commands from the project directory:

```sh
poetry env use python3.12
poetry install
docker compose up -d
poetry run python main.py
```

The API runs at http://127.0.0.1:8000; interactive documentation is at http://127.0.0.1:8000/docs.
The bank endpoint is http://localhost:8080/payments. Run a single application process because
storage is in memory. Restarting the API clears saved payments. Auto-reload is disabled.

An optional environment variable changes the bank endpoint:

```sh
BANK_URL=http://localhost:8080/payments poetry run python main.py
```

`.env.example` documents this variable; the app does not automatically load `.env` files.

## Try it

Run the standalone demo directly in PyCharm or from the terminal. No running API or Docker
is needed; it exercises the real API in process with simulated bank responses and synthetic cards:

```sh
poetry run python scripts/demo.py
```

To test against the running API and supplied Docker bank simulator instead, start both services
using the Run instructions above, then run:

```sh
poetry run python scripts/demo.py --live
```

In PyCharm, leave `main.py` running and set `--live` in the demo run configuration's parameters.
Live mode requires both services and reports startup instructions if either is unavailable.

The script generates a future expiry year. Alternatively, create a payment:

```sh
curl -i http://127.0.0.1:8000/payments \
  -H 'Content-Type: application/json' \
  -d '{"card_number":"2222405343248877","expiry_month":12,"expiry_year":2030,"currency":"GBP","amount":1050,"cvv":"123"}'
```

Update the expiry if needed. Example `201 Created` response (ID varies):

```json
{
  "id": "0b0f815b-70d5-4f33-95b7-2d5e5a3d814c",
  "status": "Authorized",
  "card_number_last_four": "8877",
  "expiry_month": 12,
  "expiry_year": 2030,
  "currency": "GBP",
  "amount": 1050
}
```

Copy the actual returned ID to retrieve the same details:

```sh
curl http://127.0.0.1:8000/payments/REPLACE_WITH_RETURNED_ID
```

The creation response also supplies the retrieval path in its `Location` header.

## API behaviour

| Request / outcome | HTTP status | Body |
|---|---|---|
| POST, bank authorizes | 201 | Saved payment with `Authorized` |
| POST, bank declines | 201 | Saved payment with `Declined` |
| POST, invalid input or malformed JSON | 400 | `Rejected` and safe field errors |
| GET, existing ID | 200 | Same payment details |
| GET, unknown or malformed ID | 404 | `{"detail":"Payment not found"}` |
| POST, network failure, timeout or bank 503 | 503 | Safe error; outcome unconfirmed |
| POST, unexpected bank status/body | 502 | Safe error; no result fabricated |

`201` means a record was created, including a declined result. Payment status describes the
bank decision. Validation errors contain `status: "Rejected"` and an `errors` list of
`field` / `message` objects. Technical errors use `detail`. Rejections and technical failures
are not saved and have no payment ID.

## Validation and assumptions

| Input | Rule |
|---|---|
| `card_number` | String of 14–19 ASCII digits |
| `expiry_month` | Integer from 1 to 12 |
| `expiry_year` | Integer from 1 to 9999; combined year/month later than current UTC year/month |
| `currency` | Exactly `GBP`, `USD` or `EUR` |
| `amount` | Strict integer in minor units; for GBP, 1050 means £10.50 |
| `cvv` | String of 3–4 ASCII digits |

All fields are required. Nulls and unexpected fields are rejected. Strict validation rejects
booleans, numeric strings and decimal values instead of converting them to integers. Card/CVV
strings preserve leading zeroes. No Luhn check is added: the brief specifies length/digits and
provides synthetic cards.

- **Expiry:** “in the future” means a later month here. The current month is rejected; accepting
  cards through month-end would be a small rule change. Later months in the current year pass.
  UTC provides one consistent timezone.
- **Amount:** the brief specifies an integer and no minimum. Zero and negative integers pass
  this exercise's validation. A positive-only requirement would mean adding `Field(gt=0)` and
  updating the boundary tests.

## Design

```text
main.py                     Local server entrypoint
payment_gateway_api/
  app.py                    Endpoints, safe errors and application construction
  models.py                 Request rules and the safe response/record model
  bank.py                   HTTP payload mapping and bank result checking
  repository.py             Dictionary storage keyed by payment ID
tests/                      Automated endpoint and simulator tests
scripts/demo.py             Repeatable HTTP demonstration
imposters/                  Unchanged supplied bank simulator
```

Flow: **validate → call bank → create safe record → save → return**. Retrieval only looks up
the ID; it never calls the bank.

- FastAPI handles routing/documentation, Pydantic centralizes validation and HTTPX calls the bank.
  Synchronous endpoints run in FastAPI's thread pool and match the synchronous bank call.
- The bank module formats expiry as `MM/YYYY`. Only an actual JSON boolean `authorized` value
  is treated as a decision. The bank authorization code is outside the required public response.
- UUIDs identify records. Each `create_app()` creates its own dictionary repository, including
  in tests. Immutable payment records can be returned without copying.
- Separate request and response models keep full cards/CVVs out of stored records and responses.
  Validation errors omit submitted values, bank error bodies are not forwarded, request model
  representations hide card/CVV, and application code never logs request bodies.
- HTTPX's five-second timeout applies to individual network operations, not the total request
  duration. No automatic retries: a lost response can mean the bank already processed the
  payment, so retrying could duplicate a charge. An uncertain outcome is never called a decline.

The starter's `.editorconfig`, `docker-compose.yml` and simulator are unchanged. Python and
dependencies are updated and pinned; `poetry.lock` is regenerated. Unused dependencies are removed.

## Tests and checks

```sh
poetry run python -m pytest
poetry run ruff check .
poetry run ruff format --check .
```

Default tests replace the outgoing HTTP call while exercising actual validation, payload mapping,
response handling and storage. They cover boundaries, both outcomes, retrieval, sensitive data,
strict types and bank failures. Expiry tests use a fixed date. Three real-simulator tests skip
unless enabled. With the supplied simulator running:

```sh
RUN_BANK_INTEGRATION=1 poetry run python -m pytest -m integration
```

The simulator authorizes odd card endings, declines even non-zero endings and returns 503 for
zero endings. The Makefile also provides `make install`, `make run`, `make test`, `make check`
and `make integration`. Stop the API with Ctrl+C; stop the simulator with `docker compose down`.

## Deliberate limits

This is a local assessment API: memory disappears on restart, workers cannot share records and
duplicate POSTs create separate attempts. There is no authentication or merchant ownership
check. UUIDs are identifiers, not access control. Full card data exists transiently for the bank
call. Use synthetic cards in the development simulator; this is not a production compliance claim.

Production work would address authenticated merchant access, durable storage, duplicate request
protection and reconciliation for unknown outcomes. Connection pooling, monitoring and a payment
card data handling design would also be needed. These are discussion points outside this scope.

Share the solution using the recruiter's instructions. Do not open a PR against `cko-recruitment`.
