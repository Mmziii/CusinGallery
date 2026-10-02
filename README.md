# Cusin Gallery — E-Commerce Platform

Production-oriented e-commerce platform for **Cusin Gallery** (kitchenware,
cookware, glassware, home goods) — Persian-language (RTL), targeting the
domain `cusin.ir`.

The project is complete end to end: a Django/DRF backend, a full React
storefront, payment architecture with a pluggable gateway abstraction,
coupons, moderated reviews, banners/daily deals, and Docker/Nginx
deployment wiring. It was built phase by phase; this README describes the
**current state of the repository**, not any single phase.

---

## What is implemented

| Area | Status |
|---|---|
| Catalog (categories, brands, products, variants, images, specifications) | ✅ API + Django Admin |
| Authentication (session + CSRF, phone/email login, password reset) | ✅ API + storefront pages |
| Cart (authenticated, server-priced, server-validated stock) | ✅ API + storefront |
| Wishlist | ✅ API + storefront |
| Checkout (address snapshot, shipping-method choice, coupon, server totals) | ✅ API + storefront |
| Shipping (standard/express, configurable costs + delivery windows, snapshotted on the order) | ✅ |
| Coupons (active/window/limits/min-order, product+category targeting, server-side math) | ✅ API + storefront |
| Orders (history, detail, ownership-scoped, immutable price snapshots) | ✅ API + storefront |
| Payments (attempts, gateway abstraction, initiate/redirect/callback/verify, idempotent, exactly-once stock decrement) | ✅ Real **ZarinPal** adapter (sandbox + production) + mock for dev/test |
| Refund tracking (required/refunded ledger, admin workflow, manual PSP refunds) | ✅ Phase C |
| Abandoned unpaid orders (`expire_unpaid_orders` cron command) | ✅ Phase C |
| Reviews (authenticated create, moderation, verified-purchase computed server-side) | ✅ API + storefront |
| Banners & daily deals (active windows, ordering, server-provided timing) | ✅ API + storefront |
| Storefront (home, shop w/ filters+search+pagination, product detail, cart, checkout, payment result, account area) | ✅ Persian/RTL, responsive |
| Owner admin — Persian Django admin: catalog w/ images+variants, order fulfilment workflow + stock restore, print label, CSV export, bulk import (CSV/Excel), coupons/banners management, `seed_demo` | ✅ |

---

## Core architectural decisions

* **Auth:** Django session authentication + CSRF. Deliberately **no JWT**.
* **Server-authoritative everything:** the client never sends prices,
  totals, discount amounts, or stock. Checkout payloads carry only an
  address selection, an optional coupon *code*, and an optional shipping
  *method id* — every number is computed server-side.
* **Money:** whole-Toman integers (`PositiveBigIntegerField`), no floats.
* **Single-mechanism modules:** pricing (`apps/products/pricing.py`),
  shipping (`apps/orders/shipping.py`), inventory decrement
  (`apps/orders/inventory.py`), coupon math (`apps/discounts/services.py`)
  each exist exactly once and are the only places their logic lives.
* **Snapshot discipline:** orders copy price totals, address, shipping
  method/cost, and delivery window at creation time. Later catalog,
  address, or settings changes never rewrite history.
* **Inventory:** decremented **only after successful payment
  verification**, exactly once (row locks + partial unique constraint on
  successful payments). Checkout never reserves stock.
* **Payments:** gateway abstraction (`apps/payments/gateways/`) with a
  real **ZarinPal** adapter (v4 API, sandbox + production, whole-Toman
  `currency=IRT`) and an HMAC-signing mock for dev/test. Every callback
  is verified server-side against the PSP, amounts are cross-checked
  against the order snapshot, and callbacks are idempotent +
  row-lock-serialized so stock decrements exactly once. Adding another
  PSP (IDPay, NextPay, …) is one new `PaymentGateway` subclass + one
  registry line + env config — see `docs/PAYMENTS.md`. No credentials
  are hardcoded anywhere, and production settings refuse to boot with
  the mock gateway.
* **Refunds:** manual (PSP panel) by design, but never invisible —
  cancelling/returning a paid order, or a verified capture that can no
  longer be applied, flags the order *refund required* with an
  accumulating amount and note journal (`apps/orders/refunds.py`); the
  owner completes it in admin with a mandatory reference note.

---

## Repository structure

```
cusin-gallery/
├── backend/
│   ├── manage.py
│   ├── requirements.txt
│   ├── .env.example
│   ├── config/
│   │   ├── settings/{base,development,production}.py
│   │   ├── urls.py, api_urls.py, wsgi.py, asgi.py
│   ├── apps/
│   │   ├── core/          # abstract base models + shared test bases
│   │   ├── accounts/      # User, Address, auth endpoints
│   │   ├── categories/    # category tree
│   │   ├── products/      # products, variants, attributes, images, pricing
│   │   ├── cart/          # authenticated server-priced cart
│   │   ├── wishlist/
│   │   ├── discounts/     # coupons + validation engine
│   │   ├── orders/        # checkout, shipping, inventory, orders API
│   │   ├── payments/      # payment attempts + gateway abstraction
│   │   ├── reviews/
│   │   └── banners/       # banners + daily deals
│   └── media/, staticfiles/
├── frontend/              # React + Vite storefront (src/, tests: lint+build)
├── docs/                  # OWNER_GUIDE.fa.md (Persian owner manual),
│                          # PAYMENTS.md (developer payment guide)
├── docker/                # backend + frontend Dockerfiles
├── nginx/                 # edge reverse-proxy config
├── docker-compose.yml
└── .env.example           # compose-level variables
```

---

## Backend setup (development)

```bash
cd backend
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then edit values (DATABASE_URL etc.)
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Requirements: **PostgreSQL** (the schema uses Postgres features —
row locks, partial unique constraints; SQLite is not a supported target).
`DATABASE_URL` accepts any format `django-environ` understands, e.g.
`postgres://user:pass@/dbname?host=/var/run/postgresql`.

Settings modules:

* `config.settings.development` (default): DEBUG on, permissive CORS,
  console email backend, LocMem cache, optional preview-tunnel support
  (`CSRF_TRUSTED_ORIGINS`, `SECURE_PROXY_SSL_HEADER`).
* `config.settings.production`: DEBUG off, refuses to start without a
  real `SECRET_KEY` / non-empty `CORS_ALLOWED_ORIGINS` / a real payment
  gateway (the mock gateway and an empty `PAYMENT_GATEWAY` are rejected,
  and `zarinpal` requires `PAYMENT_MERCHANT_ID`), secure cookies and
  HSTS gated behind `HTTPS_ENABLED=True`, shared **Redis** cache
  (`REDIS_URL`) so DRF throttling is global across gunicorn workers.

## Frontend setup (development)

```bash
cd frontend
npm install
npm run dev        # Vite dev server on :5173, proxies /api and /media to :8000
```

The dev proxy (see `vite.config.js`) keeps the browser on a single
origin, so session cookies and CSRF work with zero CORS configuration.
Build for production with `npm run build`; lint with `npm run lint`
(`eslint src --ext js,jsx`).

The API base URL defaults to the same-origin `/api/v1`. Set
`VITE_API_BASE_URL` only if the API genuinely lives on another origin
(it is a build-time variable — see `frontend/.env.example`).

---

## Tests

Backend (502 tests, all green on PostgreSQL at the time of writing):

```bash
cd backend
python manage.py test
```

Coverage highlights: registration/login/logout/ownership, catalog
filtering/search/pagination/permissions, cart ownership/stock/pricing,
checkout + shipping-method snapshots, payment success/failure/cancel,
invalid + forged + duplicate callbacks, wrong amount, repeated
verification, already-paid orders, **exactly-once inventory under
concurrent callbacks** (threaded, PostgreSQL-only — skipped on SQLite
with a documented reason), coupon rules end to end, review moderation +
verified-purchase, banners active-window filtering. Phase C adds the
**ZarinPal adapter behind a fake HTTP layer** (no network in tests:
payloads/hosts sandbox-vs-production, verify codes 100/101, `errors`
envelopes, timeouts, replayed + simultaneous callbacks, verify-timeout
stays PENDING then completes on replay), the **refund ledger** (all
automatic triggers, admin mark-refunded paths, late-capture and
duplicate-capture money races), **`expire_unpaid_orders`** (boundaries,
idempotency, dry-run, pay-after-expiry), and the **production boot
guards** (mock gateway impossible in production).

Frontend: no unit-test framework is configured; verification is via
`npm run lint` (0 problems) and `npm run build`, plus exercising the
running app against the live API.

System checks: `python manage.py check` and
`python manage.py makemigrations --check --dry-run` are clean.

---

## Payments configuration

Full developer documentation — flow diagram, security invariants,
sandbox→production runbook, how to add another gateway — lives in
**[`docs/PAYMENTS.md`](docs/PAYMENTS.md)**. Gateway selection and
credentials are **environment-only**:

| Variable | Purpose |
|---|---|
| `PAYMENT_GATEWAY` | `mock` (dev/test only — production refuses it) \| `zarinpal` (real PSP, sandbox + production). |
| `PAYMENT_MERCHANT_ID` | ZarinPal 36-char merchant id (required in production; any 36-char value in sandbox). The mock uses this slot as its HMAC signing secret. |
| `PAYMENT_ZARINPAL_SANDBOX` | `True` → sandbox.zarinpal.com (no real money); `False` → production hosts. |
| `PAYMENT_CALLBACK_URL` | Callback base URL registered with the PSP (the API view derives it from the request when possible). |
| `PAYMENT_GATEWAY_TIMEOUT` | Seconds to wait for gateway HTTP calls. |
| `ORDER_EXPIRY_HOURS` | Age threshold for the `expire_unpaid_orders` cron command. |

The **ZarinPal adapter** implements the v4 REST API end to end: payment
request, StartPay redirect, server-side verify (honoring ZarinPal's
code-101 repeat-verify semantics), `Status=NOK` cancellation, receipt
capture (`ref_id`, masked `card_pan`, card fingerprint hash), and a
strict split between "gateway unreachable" (attempt stays PENDING on
verify — the money state is unknown) and "gateway said no" (FAILED).

The **MockGateway** remains a full protocol implementation (not a
stub): it mints an authority, hosts a "gateway page", signs callbacks
with an HMAC, and verification re-checks that signature server-side —
so the whole lifecycle stays exercisable in dev/tests **without any
network access or credentials**.

Abandoned unpaid orders are cleaned up by
`python manage.py expire_unpaid_orders` (cron-safe, row-lock-checked,
never moves stock — stock is only taken at payment).

---

## Docker / deployment wiring

`docker-compose.yml` defines: `postgres` (persistent volume +
healthcheck), `redis` (shared cache for throttling), `backend`
(gunicorn, runs `collectstatic` on start; migrations are run explicitly
by the operator: `docker compose run backend python manage.py migrate`),
`frontend` (Vite build served by an internal nginx), and `nginx` (the
single edge proxy: `/api/` and `/admin/` → backend, `/static/` and
`/media/` served directly from shared volumes, everything else →
frontend).

**Honest status of the infra:** these images and configs are written and
reviewed, but this repository's development environment has no Docker
daemon or real domain, so the compose stack has not been booted here and
HTTPS has not been exercised. The nginx config ships HTTP-only with a
documented path to HTTPS (`HTTPS_ENABLED=True` + certificates + the
commented 443 server block).

---

## Remaining external requirements

These cannot be provided by the code itself and must be supplied by the
operator:

* **A real ZarinPal merchant id** for live payments — until then,
  ZarinPal's **sandbox** (`PAYMENT_ZARINPAL_SANDBOX=True`, any
  36-character merchant id) exercises the real flow, and local
  development uses the mock gateway. Production settings refuse to
  start with the mock gateway or without a merchant id, so this cannot
  be forgotten silently.
* **SMTP credentials** (`EMAIL_HOST`, …) for real password-reset
  emails (development prints them to the console).
* **A domain + TLS certificate** for production HTTPS.
* **Catalog content** — products/categories/banners are managed in
  Django Admin (`/admin/`); the application deliberately ships with no
  fake data.
* A **Redis instance** in production (compose provides one).

---

## Environment variables

See the two documented templates — **root `.env.example`** (compose-level:
Postgres credentials, `VITE_API_BASE_URL`) and **`backend/.env.example`**
(every backend setting: database, security, shipping costs/delivery
windows, email, payment gateway, `FRONTEND_URL`, `REDIS_URL`). Real
`.env` files are git-ignored and must never be committed.
