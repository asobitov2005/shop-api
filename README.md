# Shop API

An order and payment REST API for the supplied **Backend Developer Test Task — Order & Payment Service**. The required provider callback is simulated. Click Payment Link and Click Shop API are additional integration paths that use the same order and stock rules.

## What the DOCX requires

| Area | Exact task requirement | Project behavior |
| --- | --- | --- |
| Products | `GET /products` returns a paginated list containing `id`, `name`, `price`, and `stock`. Cache the list in Redis and invalidate it when stock changes. | Page and page-size parameters, Redis cache, invalidation on reservation and release. |
| Orders | `POST /orders` receives a list of `{product_id, quantity}`. Reserve stock immediately; start the order in `pending`. Two buyers competing for the last unit must not both succeed; stock must never be negative. | One PostgreSQL transaction locks product rows, validates quantities and availability, stores price snapshots, and reserves stock. |
| Payment callback | `POST /payments/callback` receives `{transaction_id, order_id, amount, status}`. `X-Signature` contains HMAC-SHA256 of the request body with a shared secret. Reject a bad signature or amount mismatch. Repeated callbacks must process the order only once; successful payment changes it to `paid`. | Verify the signature against the original body bytes, compare the amount with the stored order total, and record provider transaction IDs for idempotency. |
| Background job | Cancel orders still `pending` after 15 minutes and release their reserved stock. | A separate worker checks expiry and performs a locked, one-time cancellation. |
| Automated tests | Cover two concurrent buyers of the last item, repeated delivery of the same callback, and an invalid signature. | PostgreSQL-backed integration tests cover these and related stock/payment races. |
| Delivery | A public/shared GitHub repository, `docker-compose.yml` starting API, PostgreSQL, Redis and worker, plus a README describing setup, tests, design choices and improvements. | See the commands and design notes below. |

The task's estimate is **4–6 hours**, with a deadline of **48 hours from receipt**. The Click extension adds work beyond that estimate.

## Click extension

When Click merchant settings are configured, a newly created order includes a Click payment URL. The URL sends the customer to Click with the stored order ID and amount. Click then calls `POST /payments/click/prepare` and `POST /payments/click/complete`; these endpoints implement Click's form fields, MD5 `sign_string`, JSON responses and documented error codes. The task's `/payments/callback` remains available with its separate HMAC-SHA256 contract. A browser redirect to `return_url` does not prove payment.

The Click integration follows the official [Payment Link](https://docs.click.uz/en/click-button/), [Shop API requests](https://docs.click.uz/en/shop-api/requests), [Shop API errors](https://docs.click.uz/en/shop-api/errors) and, where a completed charge needs recovery, [Merchant API requests](https://docs.click.uz/en/merchant-api/requests).

## Run locally

```bash
docker compose up --build -d
docker compose ps
```

The API is available at `http://localhost:58000`. The Compose file also starts PostgreSQL, Redis and the expiry worker. Copy `.env.example` to `.env` to override development defaults and to configure Click. `.env` is excluded from Git; never commit merchant secrets. After startup, add example products with:

```bash
docker compose exec api python -m app.seed
```

## Run the checks

```bash
docker compose run --rm api pytest -q
docker compose run --rm api ruff check .
docker compose run --rm api ruff format --check .
```

Tests use a dedicated PostgreSQL database ending in `_test` and a separate Redis test DB. They refuse to reset a database without the `_test` suffix. Authored code files are kept under the requested 300-line maximum, checked during review with `wc -l`.

## API examples

Create an order:

```bash
curl -X POST http://localhost:58000/orders \
  -H 'Content-Type: application/json' \
  -d '{"items":[{"product_id":1,"quantity":2}]}'
```

The response includes its stored total, `pending` status, expiry time and `payment_url` when Click is configured. Product prices and totals come from the database; the client does not submit a trusted amount when placing an order.

For the simulated callback, `status` is `success` or `failed`. The DOCX specifies the field but does not define its values; this project uses `success` to mark the pending order paid and `failed` to cancel it and release stock. Sign the **exact JSON bytes** sent in the request with `TASK_WEBHOOK_SECRET` and send the lowercase hexadecimal digest in `X-Signature`. A repeated valid transaction returns its prior outcome without applying stock/payment changes again.

For example, after creating order `1` with a stored total of `5.00`, this sends a signed success callback. Export the same `TASK_WEBHOOK_SECRET` configured for the API before running it:

```python
import hashlib
import hmac
import os
from urllib.request import Request, urlopen

body = b'{"transaction_id":"demo-1","order_id":1,"amount":"5.00","status":"success"}'
signature = hmac.new(os.environ["TASK_WEBHOOK_SECRET"].encode(), body, hashlib.sha256).hexdigest()
request = Request(
    "http://localhost:58000/payments/callback",
    data=body,
    headers={"Content-Type": "application/json", "X-Signature": signature},
    method="POST",
)
with urlopen(request) as response:
    print(response.read().decode())
```

## Design choices

- PostgreSQL owns order, stock and payment state. Product rows are locked in ID order when stock is reserved; order rows are locked before payment or expiry transitions. This prevents overselling and double release.
- Money uses `Decimal` and database `NUMERIC(12,2)`; each order item stores the product's price at order creation.
- Redis only caches the paginated product list. A versioned cache key changes after committed stock updates; cached data is never the source of truth.
- The worker runs as a separate process and cancels due pending orders in batches. No Celery broker or general event framework is needed for this task.
- HTTP endpoints, order transitions and Click protocol code live in separate feature folders. Shared stock/payment rules are implemented once.

## Improvements with more time

Add authenticated customer accounts and order ownership, structured metrics/alerting for payment recovery, and a provider-approved live Click test suite. Any Click reversal must use a confirmed Merchant API `payment_id`; the public documentation does not unambiguously equate it with every Shop API identifier. Unknown network outcomes remain visible for reconciliation instead of being marked refunded without proof.
