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

The API is at `http://localhost:58000/docs`; `/` opens the shop. API startup applies Alembic migrations automatically. Choy, Qahva and Asal each sell for 1,000 UZS. The database keeps each original price and discount amount, and the seed is idempotent. Tests use a dedicated `_test` PostgreSQL database and separate Redis database.

Copy `.env.example` to a private `.env` to configure Click. Never commit merchant keys. The simulated payment callback uses `TASK_WEBHOOK_SECRET`: sign the exact JSON request bytes with HMAC-SHA256 and send the lowercase hex digest as `X-Signature`. Callback `status` values are `success` and `failed`; failure cancels a pending order and releases stock.

## Click integration

With Click credentials configured, `POST /orders` returns a [Payment Link](https://docs.click.uz/en/click-button/) URL containing the order ID and UZS total. Click sends both Shop API stages to `POST /payments/click/callback`; the `action` field routes Prepare (`0`) and Complete (`1`). Requests use Click's MD5 signatures and remain separate from the task's simulated HMAC callback. A browser return URL does not confirm payment.

For this deployment, set Click's callback URL to `https://shop.testnest.uz/payments/click/callback` in the merchant cabinet.

## Technologies

| Technology | Where and why it is used |
| --- | --- |
| Python and FastAPI | `app/`: product, order and payment callback endpoints. |
| PostgreSQL | Stores products, reserved stock, orders and payments; transactions protect concurrent orders. |
| Redis | Caches product pages and clears stale data when stock changes. |
| Python background worker | `app/worker/`: cancels pending orders after 15 minutes and restores stock. |
| HMAC-SHA256 | Verifies the signature of `POST /payments/callback`. |
| Docker Compose | Starts the API, PostgreSQL, Redis and worker together. |
| pytest | `tests/`: checks concurrent orders, repeated callbacks and invalid signatures. |
