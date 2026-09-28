# Shop API

FastAPI order and payment service for the supplied **Backend Developer Test Task — Order & Payment Service**. All database prices, order totals and payment amounts are in Uzbek so'm (`UZS`). Source: [GitHub repository](https://github.com/asobitov2005/shop-api).

## Task requirements

| Requirement from the DOCX | Implementation |
| --- | --- |
| Paginated `GET /products` with `id`, `name`, `price`, `stock`; Redis cache invalidated on stock changes | Redis page cache; invalidation after reservation or release |
| `POST /orders` with `{product_id, quantity}` items; reserve stock, start `pending`, prevent two buyers taking the last unit | PostgreSQL row locks and one transaction; stock cannot go negative |
| `POST /payments/callback` with `{transaction_id, order_id, amount, status}` and `X-Signature` HMAC-SHA256 over the raw body | Signature and amount verification; transaction ID makes 3–5 retries idempotent; success marks `paid` |
| Cancel `pending` orders after 15 minutes and restore stock | Separate worker with locked expiry batches |
| Tests for concurrent last-item orders, repeated callbacks and invalid signatures | PostgreSQL-backed tests cover these cases and related races |
| Docker Compose starts API, PostgreSQL, Redis and worker; README explains run, tests, decisions and improvements | Commands and notes below |

## Run and test

```bash
docker compose up --build -d
docker compose exec api alembic current
docker compose exec api python -m app.seed
docker compose run --rm api pytest -q
docker compose run --rm api ruff check .
docker compose run --rm api ruff format --check .
```

The API is at `http://localhost:58000/docs`. API startup applies Alembic migrations automatically. Seed products are Choy (15,000.00 UZS), Qahva (25,000.00 UZS) and Asal (45,000.00 UZS). The seed is idempotent. Tests use a dedicated `_test` PostgreSQL database and separate Redis database.

Copy `.env.example` to a private `.env` to configure Click. Never commit merchant keys. The task callback uses `TASK_WEBHOOK_SECRET`: sign the exact JSON request bytes with HMAC-SHA256 and send the lowercase hex digest as `X-Signature`. Callback `status` values are `success` and `failed`; failure cancels a pending order and releases stock.

## Click integration

With Click credentials configured, `POST /orders` returns a [Payment Link](https://docs.click.uz/en/click-button/) URL containing the order ID and UZS total. Click calls `POST /payments/click/prepare` and `POST /payments/click/complete` using the [Shop API](https://docs.click.uz/en/shop-api/requests) protocol and MD5 signatures. These are separate from the task's HMAC callback. A browser return URL does not confirm payment.

For this deployment, set Click's Prepare and Complete callback URLs to `https://shop.testnest.uz/payments/click/prepare` and `https://shop.testnest.uz/payments/click/complete` in the merchant cabinet.

## Design and limits

- PostgreSQL owns stock, order and payment state. Product rows are locked in ID order; callback and worker lock orders before status changes. Redis only caches product pages.
- Decimal money and stored item prices keep totals stable. A payment transaction is recorded once per provider transaction ID. Code is split by feature; the worker uses the same image as the API.
- With more time: add customer authentication, metrics and provider-approved live payment tests. A late successful Click charge is stored with `recovery_status=manual_review` for operator reconciliation: the public docs do not clearly map Shop IDs to the Merchant API reversal `payment_id`. Check the API service log and these database rows; do not assume a refund occurred.
