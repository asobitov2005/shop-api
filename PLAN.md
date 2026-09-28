# Order & Payment Service Implementation Plan

> **For implementation:** Build the tasks in order. Keep the test task's API contract intact; add Click as a separate integration. Mark each checkbox after its test passes.

**Goal:** Deliver the REST API described in `Backend_Test_Task.docx`, with a working Click payment link generator and Click Shop API Prepare/Complete handlers, while keeping the required simulated payment callback.

**Architecture:** FastAPI owns HTTP routes; PostgreSQL is the source of truth for products, reservations, orders and payment transactions. Redis caches the product list. A separate Python worker process cancels expired orders. The simulated callback and Click Shop API have separate protocol adapters but call the same order/payment state-transition functions.

**Tech stack:** Python 3.12, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL, redis-py, pytest/httpx. `docker compose` starts `api`, `db`, `redis` and `worker`. A small polling worker is sufficient; Celery and Beat are unnecessary here.

**Specification:** `/home/azizbek/Downloads/Telegram Desktop/Backend_Test_Task.docx`. Click references: [Shop API requests](https://docs.click.uz/en/shop-api/requests), [Shop API errors](https://docs.click.uz/en/shop-api/errors), [Payment Link](https://docs.click.uz/en/click-button/).

**Timebox:** The DOCX estimates 4–6 hours for its mandatory features and sets a 48-hour delivery window from receipt. Complete and verify the task features before spending time on the Click extension; the extension increases the actual effort.

**Review focus:** The tests below must pin down five easy-to-miss cases: two orders racing for one item (Step 1), a repeated transaction ID with changed data (Steps 2 and 5), callback racing with expiry (Step 3), cache still showing reserved stock after cancellation (Step 3), and Click Complete arriving after order expiry (Step 5).

## Mandatory engineering requirements

These are acceptance criteria from the user, not optional improvements.

- Implement every requirement in the DOCX. Click is an additional working integration; it never replaces the required simulated HMAC callback.
- Implement SOLID through clear responsibilities and explicit dependencies: routes handle HTTP, services own business decisions and transaction boundaries, and Click-specific code owns its protocol. Pass database sessions, cache clients and external clients into the code that uses them. Use small functions/classes; introduce an interface only where an actual dependency needs substitution. Any implementations of a shared interface must preserve its contract.
- Apply DRY to reservation, stock release, payment finalization and amount validation. Both payment entry points use the same business rules. Their different signature algorithms and response formats stay in their respective modules.
- Apply KISS: one application, one PostgreSQL database, Redis and one worker process. No generic repository framework, provider registry, event bus, microservices, speculative inheritance or abstractions with no concrete use.
- Organize code by feature in readable folders. Each module has one cohesive responsibility; dependencies must not form circular imports. Use meaningful names, type annotations on service boundaries, short functions and comments explaining non-obvious decisions.
- Aim for **at most 200 physical lines per authored code file; 300 is a hard maximum**, including blank lines and comments. This also applies to tests, scripts and project-owned migrations. Split by responsibility before reaching the limit; never compress statements, hide logic or create arbitrary numbered fragments to satisfy it. Markdown documentation is not code and is outside this limit.
- Add a simple repository check for the 300-line maximum and run it with lint, formatting and tests before delivery. Exclude third-party dependencies and generated build artifacts, not project-owned code.
- Deliver complete handlers and worker behavior, with no stubs, TODO implementations, swallowed errors or known unresolved correctness failures. A test result is evidence, not a guarantee of zero undiscovered bugs: fix discovered failures and document any unverified external dependency accurately.
- Real Click checkout must be implemented and verified through link → Prepare → Complete → persisted order state. Offline protocol tests are mandatory, but do not by themselves prove a live integration works. Record the controlled integration result when merchant credentials and a reachable callback URL are available; otherwise explicitly report that live verification is pending.

## DOCX coverage checklist

| Mandatory requirement | Implementation and evidence |
| --- | --- |
| Paginated products with `id`, `name`, `price`, `stock` | Products route and pagination test |
| Redis list cache; invalidate on stock changes | Cache tests for both reservation and release |
| Order with product/quantity items; reserve stock; initial `pending` | Transactional order creation and persisted-state tests |
| Two buyers for the final unit; stock never negative | Real PostgreSQL concurrent connections plus DB constraint |
| Exact task callback fields and HMAC-SHA256 `X-Signature` | Raw-body signing tests and documented request example |
| Reject invalid signature and wrong amount | Rejection tests proving no state mutation |
| Repeated callbacks processed once; success makes order `paid` | Repeat the same callback 5 times and test simultaneous duplicates |
| Cancel pending orders after 15 minutes; release stock | Worker, expiry boundary, repeat-run and payment/expiry race tests |
| Compose starts API, PostgreSQL, Redis and background worker | Clean-start smoke check |
| GitHub source, Compose file and README | Delivery checklist; README includes run/test commands, decisions and improvements |

## Scope and decisions

- All mandatory task routes remain: `GET /products`, `POST /orders`, `POST /payments/callback`.
- The task callback keeps `X-Signature: HMAC-SHA256(raw request body, TASK_WEBHOOK_SECRET)`. It is **not** changed to Click's MD5 protocol.
- Click adds `payment_url` to the order response and two separate routes: `POST /payments/click/prepare` and `POST /payments/click/complete`.
- No customer-facing frontend, invoice creation, card-token flow, user accounts or general payment-provider framework.
- Click credentials are environment variables. The task API, Docker startup and all tests work without real Click credentials. Valid merchant credentials and registered callback URLs are required to exercise real Click checkout; the late-settlement rule below is an additional live-launch gate. Never commit live secrets.
- Monetary amounts use PostgreSQL `NUMERIC(12,2)` and Python `Decimal`; order total is calculated from stored product prices, never accepted from the client.
- Order status is `pending`, `paid` or `cancelled`. A `failed` simulated payment cancels the pending order and releases its stock. These callback status values are documented in README because the task does not define an enum.
- Payment attempts are separate from order settlement. Do not add a unique constraint on `payment_transactions.order_id`; a retry must not be blocked merely because an earlier attempt exists. Unique provider transaction IDs and the locked order transition prevent duplicate processing and more than one successful local settlement. A cancelled order is not reopened by a callback.

## API contract

| Route | Input | Result |
| --- | --- | --- |
| `GET /products?page=1&page_size=20` | `page >= 1`, `1 <= page_size <= 100` | `{items: [{id,name,price,stock}], total, page, page_size}` |
| `POST /orders` | `{items: [{product_id, quantity}]}` | `201` with `{id,status,total_amount,expires_at,payment_url}`; `payment_url` is `null` if Click is not configured |
| `POST /payments/callback` | JSON `{transaction_id,order_id,amount,status}` and `X-Signature` | `success` changes pending to paid; `failed` changes pending to cancelled; an identical retry returns the prior result |
| `POST /payments/click/prepare` | Click form-urlencoded Prepare fields | Click JSON `{click_trans_id,merchant_trans_id,merchant_prepare_id,error,error_note}` |
| `POST /payments/click/complete` | Click form-urlencoded Complete fields | Click JSON `{click_trans_id,merchant_trans_id,merchant_confirm_id,error,error_note}` |

Task callback errors: invalid/missing signature → `401`; malformed payload → `422`; missing order → `404`; wrong amount or conflicting transaction/repeated payment → `409`. Verify the HMAC against the original bytes with constant-time comparison **before** parsing JSON. The signature is a lowercase hexadecimal digest; README includes a reproducible example.

Click handlers accept form-urlencoded fields and verify the documented `sign_string` MD5 formulas using the original field strings. Prepare signs `click_trans_id + service_id + SECRET_KEY + merchant_trans_id + amount + action + sign_time`; Complete inserts `merchant_prepare_id` between `merchant_trans_id` and `amount`. Do not reformat the form's amount before signature verification. Validate `service_id`, `action`, `merchant_trans_id`, amount, `click_trans_id` and (for Complete) `merchant_prepare_id`. Return Click's documented JSON error codes, including `-1` for bad signature, `-2` for wrong amount, `-5` for unknown order, `-6` for unknown prepare transaction, `-4` for already paid and `-9` for a previously cancelled transaction. A repeated Prepare for the same transaction/order/amount returns the same `merchant_prepare_id`, including when `sign_time` and the valid signature change. Conflicting order or amount for an existing transaction is rejected. A repeated successful Complete reports already paid without changing stock or order again. Distinct successful external charges must not be mistaken for a harmless replay; use the settlement recovery path below.

The Click link is built from `https://my.click.uz/services/pay` using `merchant_id`, `service_id`, formatted `amount`, `transaction_param=order.id` and `return_url` only if configured. URL-encode parameters. `return_url` is only a browser redirect; it never marks an order paid. Click's `merchant_trans_id` must map back to the same order ID.

## Data and transaction rules

- `products`: `id`, `name`, `price`, `stock`; database constraint `stock >= 0`.
- `orders`: `id`, `status`, `total_amount`, UTC `created_at`, UTC `expires_at` (`created_at + 15 minutes`).
- `order_items`: `order_id`, `product_id`, `quantity`, `unit_price` snapshot.
- `payment_transactions`: internal bigint `id`, `order_id`, `provider` (`simulated`/`click`), external transaction ID, amount, status, Click `click_paydoc_id` where present. Unique external ID per provider; multiple attempts can reference an order. The internal ID is Click's stable `merchant_prepare_id`/`merchant_confirm_id`. Keep any required settlement recovery state on this record rather than introducing a general job framework.
- `POST /orders`: validate nonempty items and positive quantities, combine repeated product IDs, lock product rows in ascending ID order, check all stock, decrement all stock and create the order/items in **one PostgreSQL transaction**. An insufficient item rolls everything back.
- Payment success, failure and expiry each lock the order row before checking its current status. Only `pending → paid` or `pending → cancelled` is allowed. Restoring reserved stock happens exactly once, in the same transaction as cancellation. A paid order never expires.
- The worker scans due pending orders in batches with `FOR UPDATE SKIP LOCKED` every 30 seconds. It is a separate Compose service using the same image and DB code; no in-process FastAPI scheduler.
- Product-list cache keys include a Redis version and pagination parameters, with a 60-second TTL. Increment the version after committed stock changes (reservation or release); old entries expire naturally. PostgreSQL remains authoritative if Redis is unavailable.

## Click-specific timing rule

Stock is already reserved at `POST /orders`, as the task requires. Click Prepare verifies that reservation and amount; it does not decrement stock again. Prepare rejects cancelled/expired orders. Complete can pay only a still-pending order; negative Click `error` cancels it and releases stock. The worker and Complete use the same order lock, so they cannot both finalize it.

A successful external charge after expiry, or a distinct second charge for an already-paid order, requires settlement recovery. Keep the local order terminal and retain the external transaction identifiers. Do not universally return `-9` and assume the funds were returned: the documented post-debit fulfillment failure flow requires acknowledging Complete and initiating reversal. Before implementing this branch, verify the exact payment-ID mapping and response behavior against Click's official contract/test environment. Implement the necessary narrow reversal operation, with persisted pending/succeeded/manual-review outcome, bounded network timeouts and safe retry/reconciliation behavior for an unknown network outcome. Use the existing worker and payment record; no invoice/card-token features or additional service. A provider rejection must remain visible for manual resolution rather than being labeled refunded. The real-payment requirement is not complete while this path is merely a placeholder. See [Merchant API requests](https://docs.click.uz/en/merchant-api/requests).

Required environment settings: `DATABASE_URL`, `TEST_DATABASE_URL`, `REDIS_URL`, `TASK_WEBHOOK_SECRET`. Click checkout requires `CLICK_MERCHANT_ID`, `CLICK_SERVICE_ID`, `CLICK_SECRET_KEY`; `CLICK_RETURN_URL` is optional. The narrow Merchant API recovery operation also needs `CLICK_MERCHANT_USER_ID`. Validate configuration as a coherent set before enabling real payments; partial configuration must produce a clear startup/configuration error. With no Click configuration, the mandatory task API still runs. Click callback URLs must be configured in the merchant account and reachable by Click.

## Planned files

```text
app/
  main.py                  # App setup and router registration
  core/
    config.py              # Validated environment settings
    db.py                  # Engine and session lifecycle
  products/
    models.py              # Product table
    schemas.py             # Product response and pagination
    router.py              # GET /products
    cache.py               # Redis reads and invalidation
  orders/
    models.py              # Order and OrderItem tables
    schemas.py             # Order input/output
    router.py              # POST /orders
    service.py             # Order creation and reservations
    transitions.py         # Shared paid/cancelled transitions and stock release
  payments/
    models.py              # Payment transaction table
    schemas.py             # Task callback input/output
    router.py              # HMAC callback transport
    service.py             # Idempotency and shared settlement coordination
    signatures.py          # Raw-body HMAC verification
    click/
      router.py            # Prepare/Complete HTTP transport
      schemas.py           # Click request/response validation
      signatures.py        # Click MD5 formulas
      links.py             # Payment URL generation
      handlers.py          # Click protocol mapped to shared services
      recovery.py          # Narrow settlement recovery and external client
  worker/
    main.py                # Polling loop, bounded failures and shutdown
    expiry.py              # Expired-order batches
  seed.py                  # Explicit idempotent demo seed
tests/
  conftest.py              # Isolated PostgreSQL/Redis fixtures
  products/               # Pagination and cache tests
  orders/                 # Stock, validation and concurrent orders
  payments/               # Task callback and idempotency
  click/                  # Link, signatures, lifecycle and recovery
  worker/                 # Expiry, repeat runs and races
scripts/
  check_file_lengths.py   # Enforce 300-line maximum
alembic/                  # Schema migrations
Dockerfile
docker-compose.yml
.env.example
pyproject.toml            # Dependencies and lint/test configuration
README.md
```

Keep this feature structure and introduce additional files only when a concrete responsibility or the line limit requires it. Framework setup belongs in `main.py`; business logic belongs in the corresponding feature. Order transitions must not import Click. Router functions call services with explicit dependencies rather than contain SQL, signing and stock logic together. Test folders contain focused test files, each respecting the same 300-line limit.

## Implementation sequence

### 1. Database, products and orders

- [ ] Create Docker/Compose skeleton, Alembic migration and DB models with constraints.
- [ ] Establish the feature folders above and the 300-line checker; configure Ruff lint/format checks. Keep product-owned Python, test and migration files within the limit throughout implementation.
- [ ] Use a dedicated test database through `TEST_DATABASE_URL`; tests must not delete or modify the runtime database. Add an explicit seed command so reviewers can create demo products without an extra product-write endpoint.
- [ ] Write failing tests for pagination, order totals, empty/invalid quantities, repeated product IDs, insufficient stock and two concurrent orders for the last item. Run against PostgreSQL, not SQLite.
- [ ] Implement `GET /products` and transactional `POST /orders`; make those tests pass.
- [ ] Add Redis caching and a test proving stock changes invalidate a previously cached page.

### 2. Exact task payment callback

- [ ] Write tests for a valid success, the same callback sent 5 times, concurrent identical callbacks, invalid signature, wrong amount, reused transaction ID with different business data, and a second successful payment attempt on the same order. Verify a changed timestamp/signature in a valid Click retry is not treated as changed business data in Step 5.
- [ ] Implement raw-body HMAC verification and the transactionally locked payment transition. Make tests pass.
- [ ] Add a failed-payment test and implement one-time stock release on failure.

### 3. Expiry worker

- [ ] Write tests for a pending order older than 15 minutes, a paid order older than 15 minutes, repeated worker runs and callback/worker races.
- [ ] Implement the separate polling worker and `FOR UPDATE SKIP LOCKED` cancellation. Make tests pass.
- [ ] Verify both order reservation and cancellation invalidate cached product stock.

### 4. Click Payment Link

- [ ] Write a test for URL host/path, URL encoding, amount with two decimals, `transaction_param` equal to the order ID, link generation with and without optional `return_url`, and `payment_url=null` with no Click configuration. Partial Click configuration must fail clearly.
- [ ] Implement link generation and include it in `POST /orders` output. Keep `return_url` server-configured.

### 5. Click Shop API

- [ ] Write offline tests from the documented Prepare/Complete field sets and MD5 formulas: valid Prepare, a valid retry with changed `sign_time`, conflicting transaction reuse, multiple attempts for one order, valid Complete, duplicate Complete, bad signature, wrong amount, wrong service/action, unknown order/prepare ID and negative Click error. Assert at most one local order settlement and no double stock mutation.
- [ ] Implement form parsing and signature verification before any state change, then Prepare/Complete through the shared order transitions. Make tests pass.
- [ ] Verify Click response fields and codes exactly match the documented protocol; do not apply task HMAC to Click routes.
- [ ] Verify the post-debit recovery contract and payment-ID mapping before implementing it; do not guess between Click identifier fields. Implement the narrow recovery behavior described above and test late successful Complete, a distinct second charge, duplicate notification, provider rejection, worker restart and unknown network outcome. Never perform network calls while holding the order DB lock.
- [ ] Exercise the complete checkout with a controlled Click merchant setup: create order, open generated link, receive Prepare/Complete and verify persisted payment/order/stock state. Record what was actually tested and resolve observed protocol errors. If credentials or public callback hosting are unavailable, record that external verification as pending instead of claiming full live success.

### 6. Delivery check

- [ ] Run `docker compose up --build` and confirm API, PostgreSQL, Redis and worker start without real Click credentials.
- [ ] Run `docker compose run --rm api pytest -q` against the dedicated test database and inspect the three task-mandated scenarios specifically.
- [ ] Run `docker compose run --rm api python scripts/check_file_lengths.py`, `docker compose run --rm api ruff check .` and `docker compose run --rm api ruff format --check .`; all must pass.
- [ ] Review responsibility boundaries, duplicated business logic, circular dependencies and transaction ownership against SOLID/DRY/KISS. Fix discovered problems without introducing unused abstractions.
- [ ] Write README: setup, `.env` variables, API examples, HMAC signing example, Click merchant setup/callback URLs, design decisions, settlement recovery behavior, actual integration verification status and improvements with more time.
- [ ] Initialize Git, commit the deliverable and prepare a public/shared GitHub repository link. Publishing the repository is a separate final action after local verification.

## Definition of done

- Every item in the DOCX coverage checklist is implemented and verified.
- `docker compose up` starts API, PostgreSQL, Redis and the worker from a clean database with migrations coordinated before DB-dependent worker operations.
- Concurrent orders never make stock negative; repeated callbacks and worker runs never double-apply payment or stock changes.
- Click link, Prepare/Complete and necessary settlement recovery are implemented, with passing protocol tests. Full live integration completion additionally requires the recorded controlled checkout; missing external access must be reported explicitly.
- All authored code files are at most 300 physical lines; lint, format and relevant tests pass. The feature folders and shared services satisfy the engineering requirements above.
- No known failing checks, incomplete handlers or unresolved discovered correctness defects remain. README explains both payment protocols, running/tests, design decisions and remaining external verification status without claiming untested success.
