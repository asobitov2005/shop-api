# Shop API

FastAPI shop API with PostgreSQL, Redis, background order expiry and Click payments. All prices, order totals and payment amounts are in Uzbek so'm (`UZS`).

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

Copy `.env.example` to a private `.env` to configure Click. Never commit merchant keys. The simulated payment callback uses `TASK_WEBHOOK_SECRET`: sign the exact JSON request bytes with HMAC-SHA256 and send the lowercase hex digest as `X-Signature`. Callback `status` values are `success` and `failed`; failure cancels a pending order and releases stock.

## Click integration

With Click credentials configured, `POST /orders` returns a [Payment Link](https://docs.click.uz/en/click-button/) URL containing the order ID and UZS total. Click calls `POST /payments/click/prepare` and `POST /payments/click/complete` using the [Shop API](https://docs.click.uz/en/shop-api/requests) protocol and MD5 signatures. These are separate from the simulated HMAC callback. A browser return URL does not confirm payment.

For this deployment, set Click's Prepare and Complete callback URLs to `https://shop.testnest.uz/payments/click/prepare` and `https://shop.testnest.uz/payments/click/complete` in the merchant cabinet.

## Design and limits

- PostgreSQL owns stock, order and payment state. Product rows are locked in ID order; callback and worker lock orders before status changes. Redis only caches product pages.
- Decimal money and stored item prices keep totals stable. A payment transaction is recorded once per provider transaction ID. Code is split by feature; the worker uses the same image as the API.
- With more time: add customer authentication, metrics and provider-approved live payment tests. A late successful Click charge is stored with `recovery_status=manual_review` for operator reconciliation: the public docs do not clearly map Shop IDs to the Merchant API reversal `payment_id`. Check the API service log and these database rows; do not assume a refund occurred.
