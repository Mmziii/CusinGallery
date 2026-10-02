# Cusin Gallery — E-Commerce Platform

Production-oriented e-commerce platform for **Cusin Gallery** (kitchenware,
cookware, glassware, home goods) — Persian-language, targeting the domain
`cusin.ir`.

This repository is being built **phase by phase**. This README documents
**Phase 1: Project Foundation** only.

---

## Tech stack

| Layer      | Technology                                              |
|------------|----------------------------------------------------------|
| Backend    | Python, Django, Django REST Framework, PostgreSQL, Gunicorn |
| Frontend   | React, Vite, React Router, Zustand, Axios                |
| Infra      | Docker, Docker Compose, Nginx, Let's Encrypt (later)      |

---

## Project structure

```
cusin-gallery/
├── backend/
│   ├── manage.py
│   ├── requirements.txt
│   ├── .env.example
│   ├── config/
│   │   ├── settings/
│   │   │   ├── base.py          # shared settings
│   │   │   ├── development.py   # local dev overrides
│   │   │   └── production.py    # production overrides + hardening
│   │   ├── urls.py              # root URLconf (admin/ + api/v1/)
│   │   ├── api_urls.py          # aggregates every app's routes under /api/v1/
│   │   ├── wsgi.py
│   │   └── asgi.py
│   ├── apps/
│   │   ├── core/                # abstract base models only (no table of its own)
│   │   ├── accounts/            # custom User model (minimal for now)
│   │   ├── categories/
│   │   ├── products/
│   │   ├── cart/
│   │   ├── wishlist/
│   │   ├── discounts/
│   │   ├── orders/
│   │   ├── payments/
│   │   ├── reviews/
│   │   └── banners/
│   └── media/                   # uploaded files (gitignored, structure kept)
│
├── frontend/
│   ├── package.json
│   ├── vite.config.js
│   ├── index.html               # lang="fa" dir="rtl"
│   ├── .env.example
│   └── src/
│       ├── main.jsx / App.jsx
│       ├── layouts/MainLayout.jsx
│       ├── pages/                (Home, NotFound — placeholders)
│       ├── services/apiClient.js # single shared axios instance
│       ├── store/useUIStore.js   # UI-only state (cart/auth are server-backed, later)
│       ├── hooks/, utils/
│       └── styles/               # design tokens + RTL-first global CSS
│
├── nginx/
│   ├── nginx.conf
│   └── conf.d/cusin.conf         # public routing for cusin.ir / www.cusin.ir
├── docker/
│   ├── backend/Dockerfile
│   └── frontend/Dockerfile + nginx.conf (internal SPA server)
├── docker-compose.yml
├── .env.example                  # root — used by docker-compose
└── .gitignore
```

---

## What Phase 1 actually contains

- A working Django project with **environment-split settings**
  (`development.py` / `production.py`) instead of one settings file with
  `if DEBUG` branches scattered through it.
- All **11 Django apps created as clean foundations** (`apps.py`, empty
  `models.py` with docstrings explaining what lands there and in which
  phase, empty `admin.py`, empty `urls.py`). No business logic, as agreed.
- **One exception, deliberately**: `apps/accounts/models.py` defines a
  minimal custom `User(AbstractUser)` model, and `AUTH_USER_MODEL` is set
  to it. This could not wait for Phase 3 — Django only allows swapping the
  user model *before* the first migration exists for it; doing it later
  requires a destructive database reset. Committing to a custom user model
  now (even empty) avoids that trap. Its real business fields (`phone`,
  email-based login, `Address` model) are Phase 3 work as planned.
- PostgreSQL-only database configuration (no SQLite anywhere, including
  dev), via `DATABASE_URL` or discrete `POSTGRES_*` variables.
- A React + Vite frontend with routing, layout, a shared Axios client, a
  UI-only Zustand store (explicitly **not** the cart/auth source of
  truth — those are server-backed per the spec and arrive with their
  phases), and an RTL-first, Persian-ready CSS foundation with design
  tokens.
- Full Docker setup: `db`, `backend`, `frontend`, `nginx` services wired
  together, with static/media files served **directly by Nginx**, never
  proxied through Gunicorn.
- An Nginx config for `cusin.ir` / `www.cusin.ir` with HTTPS left as a
  ready-to-uncomment block (no invented certificates), paired with an
  explicit `HTTPS_ENABLED` toggle in Django (see "HTTPS is off by
  default" below) so the default deployment is a genuinely working HTTP
  site rather than a broken redirect-to-nowhere.
- **The initial migration for `accounts.User` is committed**
  (`apps/accounts/migrations/0001_initial.py`). The production workflow
  is `migrate` only — see the "About the committed migrations" note below
  for how it was produced and how to verify it.
- `.env.example` at three levels (root, `backend/`, `frontend/`) — same
  variable names throughout so nothing silently diverges between running
  via Docker and running each half directly.

---

## About the committed migrations

Every model introduced through Phase 2 has its migration committed
(12 migration files across 9 apps as of this phase — see "What Phase 2
built" below for the full list and dependency order), so the normal
workflow from here on is just:
```bash
python manage.py migrate
```
**not** `makemigrations && migrate` — migrations are source code and
belong in version control, not generated on a production server.

One thing to be upfront about: **all of these files were hand-authored**,
not produced by actually running `makemigrations` — the sandbox this
project was built in has no network access, so Django itself could not be
installed to run that command for real (see the "Honesty note" section
below). What's in them was written to match each corresponding
`apps/*/models.py` field-for-field, and cross-checked with automated
(not just eyeballed) comparisons — see "Static checks actually
performed" in "What Phase 2 built" below for exactly what was verified
and how. Before you rely on any of it, verify it matches your installed
Django version:
```bash
python manage.py makemigrations --check --dry-run
```
(no app name = checks every app at once). If that says "No changes
detected", you're good — proceed straight to `migrate`. If it reports a
difference for a specific app, run `makemigrations <app>` for real and
commit whatever it produces in place of the corresponding file here.

From Phase 3 onward, as new fields/models are added, you'll run
`makemigrations <app>` again as normal — that's the ordinary way this
project's migrations grow. Only these first ones needed special
handling, because they couldn't be generated in the environment that
built them.

---

## HTTPS is off by default (and that's intentional)

`config/settings/production.py` has one flag, `HTTPS_ENABLED` (default
`False`), that gates `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`,
`CSRF_COOKIE_SECURE`, and HSTS all together.

It defaults to `False` because `nginx/conf.d/cusin.conf` currently only
has an HTTP (port 80) server block — no certificate exists yet. If those
settings defaulted to "on," Django would redirect every request to an
`https://` endpoint Nginx doesn't serve, and would mark cookies
secure-only so browsers silently stop sending them over the plain HTTP
that's actually live — breaking login and CSRF-protected requests
entirely. Deploying Phase 1 as-is over plain HTTP works correctly with
the current defaults.

To go live with HTTPS once you have real certificates:
1. Uncomment the HTTPS `server` block and the HTTP→HTTPS redirect block
   in `nginx/conf.d/cusin.conf`.
2. Set `HTTPS_ENABLED=True` in your `.env`.
3. Uncomment the `"443:443"` port mapping in `docker-compose.yml`.

No other code changes are needed — `SECURE_PROXY_SSL_HEADER` is already
correctly configured for Nginx's proxy headers either way.

---

## Getting started (local, without Docker)

**Backend**
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # then fill in SECRET_KEY at minimum
# Requires a running PostgreSQL matching your .env — see below.
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

You'll need a local PostgreSQL database matching your `.env` first, e.g.:
```bash
createdb cusin_gallery
createuser cusin_user --pwprompt
```

**Frontend**
```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

> **About `package-lock.json`:** none is committed yet — see "Frontend
> dependency reproducibility" below for why, and please run `npm install`
> once and commit the lockfile it generates. `package.json` currently
> pins exact versions (no `^` ranges) as a weaker interim guarantee.

---

## Getting started (Docker)

```bash
cp .env.example .env        # repo root — fill in SECRET_KEY, POSTGRES_PASSWORD, etc.
docker compose build
docker compose up -d
docker compose exec backend python manage.py migrate
docker compose exec backend python manage.py createsuperuser
```

Then visit `http://localhost/` (frontend) and `http://localhost/admin/`
(Django admin) on your VPS or local machine. HTTPS is not enabled yet —
see "HTTPS is off by default" above for exactly what to change once
you're pointed at the real `cusin.ir` DNS and have real certificates.

---

## What you need to configure manually

- **`SECRET_KEY`** (root `.env` and/or `backend/.env`) — generate with
  `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"`.
  Production refuses to boot without a real one.
- **`POSTGRES_PASSWORD`** — change from the placeholder before deploying.
- **Verify the committed migrations** —
  `python manage.py makemigrations --check --dry-run` (all apps) before
  your first real `migrate`. See "About the committed migrations" above.
- **`frontend/package-lock.json`** — run `npm install` once and commit
  it. See "Frontend dependency reproducibility" below.
- **Real payment gateway credentials** (`PAYMENT_GATEWAY`,
  `PAYMENT_MERCHANT_ID`) — left blank on purpose; you said you'll provide
  these later, and the payment app itself doesn't exist until Phase 7.
- **Email/SMTP credentials** — now genuinely used as of Phase 3: the
  password-reset flow sends a real email via whatever `EMAIL_BACKEND` is
  configured. In development the console backend already "delivers" it
  (prints to stdout) with no setup needed; in production, set
  `EMAIL_HOST`/`EMAIL_HOST_USER`/`EMAIL_HOST_PASSWORD`/etc. or reset
  emails won't actually send (they'll fail silently — see
  `PasswordResetRequestView`'s `fail_silently=True`, a deliberate choice
  so a misconfigured mail server doesn't turn into a 500 for the user).
- **`FRONTEND_URL`** — defaults to `https://cusin.ir`; only used to
  build the link inside password-reset emails. Change it if your
  frontend is ever served from a different origin than the API.
- **Brand assets** — drop the official logo into
  `frontend/src/assets/brand/` and swap the placeholder favicon at
  `frontend/public/favicon.svg`.
- **HTTPS certificates + `HTTPS_ENABLED=True`** — run Certbot against the
  real `cusin.ir` DNS on your actual server, then follow "HTTPS is off by
  default" above. This environment has no way to obtain real
  certificates, so nothing is faked here.
- **DNS** — point `cusin.ir` and `www.cusin.ir` at your VPS.

---

## Frontend dependency reproducibility

No `package-lock.json` is committed in this handoff. That wasn't an
oversight — it's a deliberate choice, and the reasoning matters for how
much to trust it once it does exist:

A real lockfile pins *exact resolved versions and cryptographic integrity
hashes* for every package in the dependency tree, fetched from the npm
registry at install time. Producing one requires actually talking to that
registry. This sandbox has no network access — `npm install` here fails
with a `403` from `registry.npmjs.org` — so there was no way to generate
a real lockfile. Hand-writing one with plausible-looking version numbers
and fabricated hashes would be **worse than having none**: it would look
reproducible while actually being fake, and `npm ci` would either fail
integrity checks against it or (worse) silently "succeed" while proving
nothing.

Instead:
- `package.json` now pins **exact versions** (no `^`/`~` ranges) as a
  weaker but honest interim guarantee.
- `docker/frontend/Dockerfile`'s install step checks for
  `package-lock.json` at build time: if present, it uses `npm ci`
  (the reproducible, production-correct choice); if absent, it falls back
  to `npm install` so the build still works today.

**What to do:** run `npm install` once, anywhere with normal internet
access, and commit the `package-lock.json` it produces. The very next
Docker build will automatically switch to `npm ci` with no further
changes needed.

---

## Honesty note: what could and couldn't be verified here

This was built in a sandboxed environment with **no outbound network
access**, which limited how much could be executed rather than just
reviewed:

- ✅ **Every backend `.py` file compiles** with `python -m py_compile` —
  144 backend files as of Phase 6 (models, admin, serializers, views,
  permissions, filters, pricing, services, shipping, 13 migrations
  across 9 apps, and 250 test methods total: 50 (Phase 3) + 75 (Phase 4)
  + 82 (Phase 5) + 43 (Phase 6)).
- ✅ **Migration dependency graph verified programmatically**, not just
  read by eye: parsed with Python's `ast` module and topologically
  sorted with Kahn's algorithm to confirm zero circular dependencies —
  re-run after Phase 6, still 13 files, still clean (Phase 6 added zero
  new migrations — confirmed by diffing `apps/orders/models.py`
  byte-for-byte against the approved Phase 5 archive, not just assumed).
- ✅ **Models-vs-migrations cross-checked programmatically**: field
  names, `on_delete` choices, `related_name`s, and named
  constraints/indexes were each diffed between every `models.py` and its
  migration(s) via small AST/regex scripts, not manual read-through
  alone. This caught zero drift issues in Phase 2's re-check, and did
  catch (and I fixed) one real admin bug in that phase:
  `autocomplete_fields` pointing at a model with no standalone
  registered `ModelAdmin`. Phase 3's `User.email` field/constraint
  change was checked the same way against `0004_user_email_unique.py`.
  Re-run for Phase 4's, Phase 5's, and Phase 6's apps specifically —
  confirmed unchanged, as expected (no model changes in any of them).
- ✅ **`autocomplete_fields` resolution re-checked project-wide** after
  every phase's admin changes — all usages across every app still
  resolve to a model with its own registered `ModelAdmin` +
  `search_fields`. (Phase 6 added no new admin registrations —
  `apps/orders/admin.py` was already adequate from Phase 2 and is
  confirmed byte-for-byte unchanged.)
- ✅ **URL ↔ view consistency checked programmatically** for every phase
  that added routes, including Phase 6: every `reverse()` call across
  the 43 new test methods was cross-referenced against the actual
  registered URL names in `apps/orders/urls.py`, and every view class
  referenced from that file was confirmed to exist in `views.py` — via a
  small script comparing the two sets, not by reading and trusting each
  reference individually.
- ✅ **`docker-compose.yml` was parsed with PyYAML** — valid YAML, and
  service names/volume mounts were manually cross-checked against
  `nginx/conf.d/cusin.conf` and the Dockerfiles for consistency (upstream
  names, static/media paths, build contexts).
- ✅ **`package.json` was validated as JSON** (unchanged this phase — no
  new frontend dependency was needed for the order/checkout data layer).
  Every new/changed frontend `.js` file (`orderApi.js`, `useOrders.js`,
  `useAsync.js`, and the refactored `useCatalog.js`) was syntax-checked
  with `node --check`, and every relative `import` path across the whole
  `frontend/src/` tree was verified to resolve to a real file via a
  small script — not assumed. (Pre-existing `.jsx` files fail
  `node --check` itself with an `ERR_UNKNOWN_FILE_EXTENSION` — a Node
  tooling limitation unrelated to their actual validity; Vite/Babel
  handles JSX correctly at build time. This affects only files already
  present since Phase 1, not anything written this phase.)
- ✅ **Diffed file-by-file against the previous approved archive at each
  phase boundary** — Phase 2 against Phase 1 v2, Phase 3 against Phase
  2, Phase 4 against Phase 3, Phase 5 against Phase 4, and this Phase 6
  against the approved
  Phase 4 archive — to confirm each phase's changes stayed inside its
  actual scope. Phase 5 touched exactly: `apps/cart/{permissions,serializers,services,urls,views,admin}.py`
  and its new `tests/` package, `apps/wishlist/{serializers,urls,views,admin}.py`
  and its new `tests/` package, `config/api_urls.py` (docstring only),
  and five new frontend files. Every other app, and all of Phase 1-4's
  settings/Docker/Nginx/accounts/categories/products, is untouched.
- ✅ **82 new test methods are real, written code** — reviewed by hand
  for correctness, and this phase's own review caught three genuine bugs
  before they became your problem to find (see "What Phase 5 built"
  above): a missing `is_active` re-check on cart quantity updates, a
  missing `select_related` causing 2 extra queries per cart-item
  mutation, and a malformed wishlist query parameter that would have
  caused an uncaught `500` instead of a clean `400`. Each has a
  dedicated regression test. None of these 207 tests (across all
  phases) have actually been executed, for the reason below.
- ❌ **`npm install` / `vite build` could not be run** — the registry
  request returned `403 Forbidden` in this sandbox (no network egress),
  re-confirmed this phase, not assumed stale from Phase 1.
- ❌ **`pip install` / `python manage.py check` / `migrate` /
  `makemigrations --check` / `python manage.py test` could not be run**
  for the same reason — no PyPI access in this sandbox, re-confirmed
  immediately before finalizing this phase (not just assumed stale from
  earlier). This is exactly why every migration file is flagged as
  hand-authored rather than machine-generated — see "About the committed
  migrations" above for how to verify them on your side.
  What the checks above *can't* catch: things only wrong at actual
  Postgres DDL-execution time (Phase 6 leans on this more than most —
  `select_for_update()` locking behavior is a genuinely Postgres-specific
  runtime concern that static analysis cannot confirm), a real Django
  version's exact autogenerated index-name hashing, or whether these 250
  written tests actually pass when run for real. That's precisely why
  `python manage.py test` is listed as a first step below, not an
  optional suggestion.

**What this means for you:** run `pip install -r requirements.txt &&
python manage.py makemigrations --check --dry-run && python manage.py
check && python manage.py test` as your first steps after unzipping, in
addition to `npm install && npm run build` on the frontend. If any of
these surfaces an issue, it's a real one I couldn't catch here, and I'd
want to fix it before Phase 7 builds on top of it — flag it and I'll
correct it directly rather than working around it.

---

## What Phase 2 built

Phase 2 (Database Architecture & Models) delivered the full relational
schema the rest of the platform builds on — models, Django Admin, and
migrations for every app except `payments` (deliberately still deferred
to Phase 7, see below).

**Models added, by app:**

| App | Models |
|---|---|
| `accounts` | `User.phone` (new field), `Address` |
| `categories` | `Category` (self-referencing tree) |
| `products` | `Brand`, `Product`, `ProductImage`, `ProductAttribute`, `ProductAttributeValue`, `ProductVariant` |
| `cart` | `Cart`, `CartItem` |
| `wishlist` | `WishlistItem` |
| `discounts` | `Coupon`, `CouponUsage` |
| `orders` | `Order`, `OrderItem` |
| `reviews` | `Review` |
| `banners` | `Banner`, `DailyDeal` |
| `payments` | *(none yet — Phase 7)* |

**Dependencies added:** `Pillow==10.4.0` in `backend/requirements.txt`.
Required by Django's `ImageField` at model/system-check time (not just at
actual upload time) — `python manage.py check` fails immediately without
it. Needed as of this phase because four fields are now `ImageField`s:
`categories.Category.image`, `products.Brand.logo`,
`products.ProductImage.image`, `banners.Banner.image`. No other new
dependencies were added — image *upload handling/processing* in the
frontend is still later-phase work; this is only the library Django
itself requires to define these fields at all.

**Design decisions worth knowing about:**
- **Pricing is whole-Toman integers** (`PositiveBigIntegerField`), not
  `DecimalField` — matches the frontend's `formatPrice()` utility from
  Phase 1, which already assumes plain integers.
- **Orders snapshot everything.** `Order`'s shipping address and every
  `OrderItem`'s product name/SKU/price are flat, copied fields — never a
  live FK to `Address` or a live read of `Product.price`. Editing a
  saved address or repricing a product later can never rewrite a past
  order.
- **`discounts` ↔ `orders` circular reference, resolved without a
  circular migration.** `Order.coupon` points at `Coupon`, and
  `CouponUsage.order` points back at `Order`. That's split as
  `discounts.0001` (Coupon) → `orders.0001` (Order) →
  `discounts.0002` (CouponUsage) — a clean line, not a cycle. The
  Python-level circular import this could otherwise cause is avoided
  with Django's lazy `"app_label.Model"` string FK references. This is
  formally verified, not just asserted — see "Static checks actually
  performed" below.
- **`CartItem` uniqueness correctly handles NULL `variant`.** A single
  `UniqueConstraint(fields=["cart", "product", "variant"])` would NOT
  actually prevent duplicate rows for products with no variant —
  Postgres (like SQL generally) treats every `NULL` as distinct from
  every other `NULL`, so a nullable column inside a plain unique
  constraint silently allows unlimited duplicates wherever it's `NULL`.
  This is enforced as two conditional (partial) constraints instead —
  `(cart, product)` unique where `variant IS NULL`, and
  `(cart, product, variant)` unique where `variant IS NOT NULL` — at the
  database level, not just in `clean()`.
- **A few more real database-level constraints**, not just admin-form
  validation: at most one default `Address` per user, at most one
  primary `ProductImage` per product, one `Review` per user per
  product, one `Coupon` redemption tracked per use — all as partial
  unique indexes or unique constraints, enforced even against a bulk
  update or a future bug.
- **No checkout, payment, or full auth logic** — per the phase scope,
  `Order.generate_order_number()` exists only so the model is usable in
  isolation (admin-created orders, seed data); cart→order conversion,
  stock decrement, and payment kickoff are Phase 6/7 work.

**Migration order** (also enforced by Django itself via each file's
`dependencies`):
```
categories.0001 → products.0001 → discounts.0001 (Coupon)
                                 → orders.0001 (needs discounts.0001)
                                 → discounts.0002 (CouponUsage, needs orders.0001)
accounts.0001 → 0002 (phone) → 0003 (Address)
cart.0001, wishlist.0001, reviews.0001, banners.0001 → each depends on products.0001
```

**Static checks actually performed** (see the "Honesty note" section for
what's still unverified without a real Django install):
- Every backend `.py` file compiles (`py_compile`).
- **Migration dependency graph parsed with Python's `ast` module and
  topologically sorted with Kahn's algorithm** — confirms zero circular
  dependencies across all 12 migration files, not just by inspection.
- **Automated field-name diff** between every `models.py` and its
  migration(s) — confirms no model field is missing from its migration.
- **Automated `on_delete` and `related_name` comparison** between models
  and migrations, app by app — all match.
- **Automated `autocomplete_fields` resolution check** across every
  `admin.py` — confirms every field referenced actually points at a
  model with its own registered `ModelAdmin` and `search_fields` (this
  caught and fixed one real bug: `ProductVariant` needed a standalone
  admin registration, not just an inline, for `CartItemInline`'s
  autocomplete to work).
- Named constraints/indexes cross-checked between models and migrations,
  including the two conditional `CartItem` constraints specifically
  (constraint names and `Q()` conditions confirmed equivalent between
  `models.py` and the migration).
- `docker-compose.yml` re-validated as YAML, `package.json` as JSON.
- Diffed against the Phase 1 v2 archive to confirm the foundation
  (settings, Docker, Nginx, `apps/core`, `apps/payments`) is untouched,
  and diffed against the previous Phase 2 archive to confirm this
  correction round touched exactly the 4 files it should have
  (`cart/models.py`, `cart/migrations/0001_initial.py`,
  `requirements.txt`, this README) and nothing else.
- Re-attempted `pip install`/network access before writing this section,
  specifically so this claim wouldn't go stale — still unavailable in
  this sandbox (see "Honesty note" below).

## What Phase 3 built

Phase 3 (Authentication and Accounts) delivered a complete, real
authentication and customer-account system on top of Phase 2's `User`
and `Address` models — no new business apps, just `apps.accounts` filled
in, plus the settings changes that decision required.

### Authentication architecture

**Session + CSRF, not JWT/tokens.** Justification (also in
`config/settings/base.py`'s `REST_FRAMEWORK` comment): this project's
own architecture already puts the frontend and API on the same origin —
Nginx serves both `cusin.ir/` and `cusin.ir/api/` from one edge (see
`nginx/conf.d/cusin.conf`). That's exactly the case session auth is the
safer default for: httponly session cookies can't be read by JS at all
(unlike a JWT sitting in localStorage, which XSS can read directly),
Django's session framework is mature and already part of the framework,
and CSRF — session auth's one real extra requirement — was already fully
wired in Phase 1 (`CsrfViewMiddleware`, `CSRF_TRUSTED_ORIGINS`,
`CSRF_COOKIE_SAMESITE`). JWT's usual justification (a genuinely
separate-origin API, or native mobile clients with no cookie jar)
doesn't apply here. `rest_framework.authtoken`, present since Phase 1/2
as an unused placeholder, was removed this phase for the same reason —
an inert second auth backend is exactly the "multiple systems for
completeness" anti-pattern to avoid.

**How login actually works**, since it's a deliberately non-default
path: `USERNAME_FIELD` stays `username` (unchanged from `AbstractUser`)
rather than being switched to `phone`/`email` — actually changing it
would mean overhauling the user manager and re-deriving
uniqueness/authentication semantics from `AbstractBaseUser`, a change
this project has no way to verify end-to-end without a working Django
install (see "Honesty note" below). Instead: registration sets
`username = phone` directly (phone numbers already satisfy Django's
default username character rules), and the login endpoint looks a user
up by phone *or* email manually and checks the password directly,
without going through `authenticate()`/auth backends at all. This
delivers the desired customer-facing behavior (log in with phone or
email) without touching the harder-to-verify machinery. **Django admin
login at `/admin/` is completely unaffected** — it still authenticates
staff by `username`/password through Django's own built-in login view,
entirely separate from these customer-facing endpoints; being staff or
superuser has no special meaning through the API below.

### Endpoints (all under `/api/v1/accounts/`)

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `csrf/` | none | Sets the CSRF cookie; call once on app load before any POST |
| POST | `register/` | none | Create an account (phone required, email optional); auto-logs in |
| POST | `login/` | none | `{identifier, password}` — identifier is phone or email |
| POST | `logout/` | session | Flushes the session server-side |
| GET | `me/` | session | Current user (no `username` in the response — internal detail) |
| PATCH | `me/` | session | Update `first_name`/`last_name`/`email` only — **not** `phone` |
| POST | `me/change-password/` | session | `{current_password, new_password, new_password_confirm}` |
| POST | `password-reset/` | none | `{identifier}` — always returns the same generic response |
| POST | `password-reset/confirm/` | none | `{uid, token, new_password, new_password_confirm}` |
| GET/POST | `addresses/` | session | List / create — scoped to the caller only |
| GET/PATCH/DELETE | `addresses/{id}/` | session | 404s (not 403) for another user's address — see below |
| POST | `addresses/{id}/set-default/` | session | Atomically swaps the default address |

**Why `phone` isn't editable via `PATCH me/`**: changing the phone number
an account logs in with should require re-verification (an SMS OTP
flow), and no SMS provider is configured anywhere in this project. This
is explicitly future-phase work, not something to fake here.

**Why another user's address 404s instead of 403ing**: `AddressViewSet`
scopes its queryset to `request.user`'s own addresses before any
object-level permission check even runs, so another user's address isn't
just forbidden — it doesn't exist from the requester's point of view.
`IsOwner` (in `permissions.py`) is a second, independent layer of the
same guarantee, kept even though the queryset scoping alone is
sufficient, as defense-in-depth against a future `get_queryset()` change.

**A non-obvious status-code detail, in case it looks like a bug**:
requests to a protected endpoint with no session return **403**, not
401. With `SessionAuthentication` as the only registered authenticator
(no `BasicAuthentication`), there's no `WWW-Authenticate` challenge to
offer, so DRF's `handle_exception` downgrades `NotAuthenticated` to
`PermissionDenied` (403) before rendering the response. This is standard
DRF behavior for session-only APIs, asserted and explained in the tests
(`tests/test_login_logout.py`).

### Password reset: real, not faked

The request/confirm flow uses 100% Django built-ins — `PasswordResetTokenGenerator`
for the token, `send_mail()` for delivery — no external service, no
invented credentials. In development, `EMAIL_BACKEND` is the console
backend (Phase 1), so a reset email genuinely prints to the console;
in production it requires real `EMAIL_HOST`/etc, already documented as
manual configuration since Phase 1. **What's explicitly NOT implemented**:
SMS delivery for phone-only accounts. No SMS provider is configured
anywhere in this project, and the master spec says not to hardcode one
— a phone-only account gets the same generic success response as
everyone else, but no message is actually sent (logged instead, so the
gap is visible in server logs rather than silent). Wiring a real SMS
provider is future-phase work.

Every response from `password-reset/` is identical whether or not an
account matches — deliberately, to avoid account enumeration.

### Settings changes this phase required

- `rest_framework.authtoken` removed from `INSTALLED_APPS`;
  `TokenAuthentication` removed from `DEFAULT_AUTHENTICATION_CLASSES`.
- `DEFAULT_THROTTLE_CLASSES`/`DEFAULT_THROTTLE_RATES` added — scoped
  (`ScopedRateThrottle`), not blanket: `register` (10/hour), `login`
  (10/min), `password_reset` (5/hour). Any endpoint that doesn't
  explicitly set `throttle_scope` is completely unaffected.
- `FRONTEND_URL` setting added (new env var, default `https://cusin.ir`)
  — used only to build the link inside password-reset emails.

### Migration (new, not a hand-edit of an applied one)

`apps/accounts/migrations/0004_user_email_unique.py` — makes
`User.email` nullable with a conditional (partial) unique constraint,
mirroring the same NULL-vs-empty-string pattern already used for `phone`
(Phase 2) and `CartItem.variant` (Phase 2 correction round): with email
optional for customers, a plain `unique=True` would incorrectly reject
the *second* customer who simply left email blank, since Postgres treats
two empty strings as duplicates (unlike two `NULL`s). This is a genuinely
new migration, not an edit to `0001`-`0003`, per this phase's own
instruction not to hand-edit an already-applied migration.

### Tests

50 real test methods across `apps/accounts/tests/` (`test_registration.py`,
`test_login_logout.py`, `test_profile.py`, `test_password.py`,
`test_addresses.py`), using `rest_framework.test.APITestCase`. These
assert actual behavior, not just status codes — e.g. that a registered
password is stored hashed (`check_password()` succeeds, raw string
comparison fails), that a session genuinely stops working after logout
(not just that logout returns 200), that setting a second default
address actually flips the first one back via the real Phase 2 database
constraint (not just that the API call succeeds), and that a used
password-reset token is rejected on reuse.

---

## What Phase 4 built

Phase 4 (Products & Catalog) turned Phase 2's existing schema
(`Category`, `Brand`, `Product`, `ProductImage`, `ProductAttribute`/
`Value`, `ProductVariant`) into a real, public, read-only catalog API,
plus the frontend service layer that consumes it. **No model or
migration changes were needed or made** — verified by diffing
`apps/categories/models.py` and `apps/products/models.py` byte-for-byte
against the approved Phase 3 archive (see "Static checks actually
performed" below).

### Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/categories/` | List active categories (paginated) |
| GET | `/api/v1/categories/{slug}/` | Category detail, incl. `product_count` |
| GET | `/api/v1/categories/tree/` | Nested hierarchy for nav menus (depth-bounded, see below) |
| GET | `/api/v1/brands/` | List active brands |
| GET | `/api/v1/brands/{slug}/` | Brand detail |
| GET | `/api/v1/products/` | List active products — filtering/search/sort/pagination, all combinable |
| GET | `/api/v1/products/{slug}/` | Full product detail — images, variants, specifications, related products |

**Every one of these is entirely read-only** (`ReadOnlyModelViewSet` —
there is no create/update/delete route registered at all, for anyone,
staff included). Catalog data is only ever modified through Django
Admin. This is deliberate, not a gap: it means there's no separate
write-API surface to secure in the first place, which is a stronger
guarantee than "protected by a permission class" — see
`apps/products/tests/test_permissions.py`, which asserts this for
anonymous, logged-in-customer, *and* logged-in-staff requests alike.

**`brands/` is mounted at the top level** (`/api/v1/brands/`, not nested
under `/products/`), matching the master spec's suggested convention,
even though `Brand` is still modeled inside `apps.products` (no separate
`brands` app was created, per the instruction not to restructure
existing apps unnecessarily) — see `config/api_urls.py`'s comment for
exactly how that's wired.

### Product list: filtering, search, sorting, pagination

All via query params on `GET /api/v1/products/`, freely combinable:

| Param | Example | Behavior |
|---|---|---|
| `category` | `?category=cookware` | Category slug (exact) |
| `brand` | `?brand=persia-steel` | Brand slug (exact) |
| `min_price` / `max_price` | `?min_price=100000&max_price=500000` | Toman range, inclusive |
| `in_stock` | `?in_stock=true` | `true` = `stock_quantity > 0`, `false` = out of stock |
| `is_featured` / `is_new` / `is_best_seller` | `?is_featured=true` | Exact boolean match |
| `search` | `?search=steel` | Matches name, SKU, short description, brand name, category name |
| `ordering` | `?ordering=price_asc` | One of `newest` (default), `oldest`, `price_asc`, `price_desc` |
| `page` | `?page=2` | Standard `PageNumberPagination` (Phase 1) — `{count, next, previous, results}` |

**No `popularity` sort option** — deliberately. No real sales/order/view
data exists yet (that needs Phase 6+), and the master spec explicitly
says not to invent a metric that isn't backed by real data. An
unsupported `ordering` value returns `400`, not a silent fallback.

### Pricing: one mechanism, not duplicated per view

`apps/products/pricing.py` is the single place price/discount display
logic lives — every serializer that shows a price calls
`price_info_for_product()` or `price_info_for_variant()` rather than
recomputing it. Two independent signals are exposed, deliberately not
conflated: `discount_percentage` is the admin-set badge value from
`Product.discount_percentage` (Phase 2), shown as entered; `is_on_sale`
/ `discount_amount` / `compare_at_price` are derived purely from
`price` vs `compare_at_price`. A variant with its own price override
shows that price plainly, without the parent product's discount info —
that comparison was set against the product's own price, not the
variant's, so applying it would show a discount that doesn't correspond
to real data.

### Inventory: coarse status only, not raw numbers

Every catalog response exposes `stock_status` (`in_stock` / `low_stock`
/ `out_of_stock`) and `is_in_stock` (bool) — never the raw
`stock_quantity` or `low_stock_threshold` values, per master spec
section 20 ("do not expose internal inventory details beyond what the
storefront needs"). Asserted directly in
`test_detail.py::test_exact_stock_quantity_is_never_exposed`.

### Product detail: specifications, derived honestly from what exists

Phase 2's schema attaches attribute values to **variants**, not directly
to products — there's no separate product-level "spec sheet" table.
`specifications` in the product detail response is derived from the
union of a product's active variants' attribute values, grouped by
attribute name with duplicates removed (e.g. Color variants Red/Blue/
Green → `{"attribute": "Color", "values": ["Red", "Blue", "Green"]}`). A
product with no variants has no specifications from this mechanism —
that's an honest reflection of what data exists, not a bug. A dedicated
product-level specifications model, independent of purchasable variant
choices, would be a reasonable schema addition in a future phase if the
store needs specs unrelated to any variant.

### Related products

One extra query, only on the single-object detail view (same category,
active, excludes self, capped at 6) — deliberately **not** offered on
the list view, where it would be a genuine per-row N+1.

### N+1 avoidance (and the query-count tests that check it)

- Product list: `select_related("category", "brand")` +
  `prefetch_related` for images (ordered so the primary image sorts
  first) — both exist specifically so a page of up to 20 products (Phase
  1's `PAGE_SIZE`) costs a constant number of queries, not one per
  product.
- Category tree: Django has no native "prefetch arbitrarily deep"
  primitive for a self-referencing tree, so `GET /categories/tree/` uses
  a **depth-bounded** nested `Prefetch` (`TREE_PREFETCH_DEPTH = 4` in
  `apps/categories/views.py`) — a fixed, small number of queries
  (one per level) instead of an open-ended per-node N+1. A 5th-level-deep
  category would be excluded from this endpoint, not silently broken.
- Product detail: `get_variants` and `get_specifications` originally
  each independently re-queried the product's variants — caught during
  this phase's own review (not by a test) and fixed to share one cached
  fetch per serializer instance.
- Tests assert this by **comparing query counts across different data
  sizes** (e.g. 3 vs 15 products), not pinning one fragile literal
  number — what actually matters is that the count doesn't scale with
  N, not that it equals some specific value that could shift for
  unrelated reasons.

### A real bug caught and fixed during this phase's own review

`CategorySerializer` initially exposed a `parent_slug` field via
`SlugField(source="parent.slug")`. DRF's dotted-source attribute
traversal only catches `django.core.exceptions.ObjectDoesNotExist`, not
the plain `AttributeError` that `getattr(None, "slug")` raises — and
most categories are top-level (`parent=None`), so this would have
crashed on exactly the common case, not an edge case. Fixed with an
explicit `SerializerMethodField` that checks `obj.parent_id` first, and
locked in with a regression test
(`test_top_level_category_has_null_parent_slug_without_error`).

### Frontend integration

`frontend/src/services/catalogApi.js` — one function per endpoint above,
all going through the shared `apiClient` from Phase 1. Deliberately just
the data layer: `frontend/src/hooks/useCatalog.js` adds small, generic
`useProducts`/`useProduct`/`useCategories`/`useCategoryTree` hooks on
top (a shared `useAsync` internally, not four copies of the same
loading/error state machine). **No pages or visual components were
built** — per the phase's own instruction not to build the final
storefront yet; this is the reusable data layer later frontend phases
build on.

### Tests

75 test methods across `apps/categories/tests.py` and
`apps/products/tests/` (`test_brands.py`, `test_list.py`,
`test_detail.py`, `test_permissions.py`, `test_performance.py`),
covering: category list/detail/tree/product-counts, brand list/detail,
product filtering (category/brand/price range/availability, individually
and combined), sorting (including the invalid-value 400 case),
pagination (including together with filtering), search, full detail
payload (pricing, stock status, images, specifications, variants,
related products), permission enforcement for anonymous/customer/staff
alike, and N+1 regression guards via query-count comparison.

---

## What Phase 5 built

Phase 5 (Cart and Wishlist) turned Phase 2's existing `Cart`/`CartItem`/
`WishlistItem` schema into real, authenticated, server-authoritative
APIs, plus the frontend data layer that consumes them. **No model or
migration changes were needed or made** — verified by diffing
`apps/cart/models.py` and `apps/wishlist/models.py` byte-for-byte
against the approved Phase 4 archive.

### Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/cart/` | Current user's cart (auto-created on first access) |
| DELETE | `/api/v1/cart/` | Clear the cart (removes all items, keeps the Cart row) |
| POST | `/api/v1/cart/items/` | Add an item — `{product_id, variant_id?, quantity}` |
| PATCH | `/api/v1/cart/items/{id}/` | Update quantity — `{quantity}` (`0` removes the item) |
| DELETE | `/api/v1/cart/items/{id}/` | Remove an item |
| GET | `/api/v1/wishlist/` | List the user's wishlist (bare array, not paginated) |
| POST | `/api/v1/wishlist/items/` | Add a product — `{product_id}` (duplicate add is graceful, not an error) |
| DELETE | `/api/v1/wishlist/items/{id}/` | Remove an item |
| GET | `/api/v1/wishlist/check/?product={id}` | `{"is_wishlisted": bool}` — for a single product's heart icon |

Every one of these requires authentication (session + CSRF, same
mechanism as every other authenticated endpoint since Phase 3 — no
second auth system introduced). There is no cart/wishlist identifier
anywhere in the request surface — the cart and wishlist are always
resolved from `request.user` server-side, so there's no parameter for
an attacker to even attempt substituting to reach another user's data.

### Pricing: reused, not duplicated

Every cart line's price comes from `apps.products.pricing` (Phase 4) —
`price_info_for_product()`/`price_info_for_variant()` — the exact same
mechanism the public catalog API uses. Nothing is stored on `CartItem`
itself; `apps/cart/services.py::build_cart_view()` recomputes price and
availability **fresh on every read**. A product repriced or deactivated
after being added to a cart is reflected immediately on the next `GET`
— the cart is explicitly not a price snapshot (that's what `Order` will
be, in a later phase). The write serializers (`AddCartItemSerializer`,
`UpdateCartItemSerializer`) have no price field at all — there is
nothing for a client to override even if it tried.

### Availability: consistent with Phase 4's privacy stance

Cart responses expose `stock_status` (`in_stock`/`low_stock`/
`out_of_stock`) and `is_available` — never raw `stock_quantity` or
`low_stock_threshold` values, matching the same coarse-status-only
approach the public catalog API already established in Phase 4.
Unavailable lines (inactive product/variant, or a stored quantity that
now exceeds current stock) **stay in the cart response**, clearly
flagged via `unavailable_reason` (`product_unavailable` /
`variant_unavailable` / `insufficient_stock`) — never silently dropped,
so a customer doesn't lose track of what's in their cart — but are
excluded from `subtotal`/`total`.

### NULL-variant handling, preserved from the Phase 2 correction round

Adding the same product twice increments the existing line rather than
creating a duplicate — enforced both at the application level (`services.add_item`
looks up the existing line first) and at the database level via Phase 2's
two conditional partial constraints (`unique_cart_product_no_variant` /
`unique_cart_product_variant`), which this phase left completely
untouched. A product added both with and without a variant correctly
produces two separate lines, not a collision.

### Concurrency: locking where it's actually needed, not everywhere

`services.add_item`/`update_item_quantity` use `select_for_update()` on
the specific `CartItem` row being changed — this prevents a lost update
if the *same user* sends two concurrent requests for the *same* cart
line (a double-click, two open tabs). It deliberately does **not** lock
the `Product`/`ProductVariant` row itself: doing so would serialize
every "add to cart" for a popular product across *all* users against
each other, for a guarantee this phase was never asked to provide — true
stock reservation is explicitly deferred to Checkout/Order (a later
phase). This tradeoff is documented directly in `services.py`'s
`add_item` docstring, not left ambiguous.

### Wishlist: reuses the catalog's own product serializer

`WishlistItemSerializer.product` is `apps.products.serializers.ProductListSerializer`
directly — a wishlisted product shows exactly the same card data (image,
price, stock status) a catalog listing does, not a reinvented shape.
This does not couple the wishlist and cart domains to each other (they
stay independent, per this phase's own instruction); both simply share
the same catalog serializer as their common dependency. A product that
becomes inactive after being wishlisted stays visible in the list,
flagged via `is_available: false`, rather than vanishing or breaking the
endpoint.

### Bugs found and fixed during this phase's own review

Three real, non-hypothetical bugs were caught by re-reading the code
critically before writing tests — not left for you to discover:

1. **`update_item_quantity` didn't re-check `is_active`.** It validated
   stock but not whether the product/variant had since been deactivated
   — meaning a customer could *increase* the quantity of an item whose
   product had become unavailable, even though the add-fresh path
   correctly blocked that. Fixed: any positive quantity change is now
   blocked for an inactive product/variant; removal (`quantity: 0`)
   remains allowed regardless, since there's no reason to block clearing
   out a discontinued line.
2. **`CartItemDetailView.get_object` had no `select_related`.**
   `update_item_quantity` accesses `cart_item.product`/`cart_item.variant`
   directly — without it, each was a separate lazy query on every single
   PATCH/DELETE request.
3. **`WishlistCheckView` read `request.query_params.get("product")`
   directly into a queryset filter.** A malformed `?product=abc` would
   reach `WishlistItem.objects.filter(product_id="abc")` and raise an
   uncaught `ValueError` — a `500`, not a clean `400`. Fixed with a
   proper `WishlistCheckSerializer` validating the input first.

Also reviewed and fixed for query efficiency (not correctness bugs, but
real N+1s): both `CartAdmin` and `WishlistItemAdmin`'s admin changelist
`list_display` FK columns (`user`, `product`) were triggering a lazy
query per row — Django Admin does not `select_related` these
automatically. Fixed with `list_select_related` and an annotated
`Count()` for `CartAdmin`'s item-count column.

### Frontend data layer

`frontend/src/services/cartApi.js` and `wishlistApi.js` — plain
functions over the existing shared `apiClient` (Phase 1), verified
field-for-field against the actual backend serializers rather than
assumed. `frontend/src/store/useCartStore.js` is a Zustand store — the
same `create()` pattern Phase 1's `useUIStore.js` already established
(no second state-management system) — fulfilling exactly what that
file's own docstring predicted: server-authoritative cart state, callable
from anywhere in the tree for a shared item-count badge. Every store
action calls the API, then writes the server's fresh response into
state; nothing is computed client-side.

Wishlist deliberately uses a **plain hook**
(`frontend/src/hooks/useWishlist.js`), not a second Zustand store —
wishlist status is naturally checked per-product (`useWishlistStatus`,
built on the dedicated `check/` endpoint) rather than needing one global
list synchronized everywhere the way a cart badge does; adding a second
global store for its own sake would be exactly the "unnecessary global
state" this phase was told to avoid.

`frontend/src/utils/apiError.js` normalizes DRF's several different
error response shapes (400 validation errors, 403/404s, network
failures) into one consistent object both the cart store and wishlist
hook use, so error handling doesn't need to be re-derived per call site.

**Guest cart is explicitly not implemented.** The master spec allows
deferring this if undocumented elsewhere, and it is: there is no
anonymous/session-based cart anywhere in this phase — `Cart` remains
strictly one-per-authenticated-user (Phase 2's `OneToOneField`), and
every cart endpoint requires login. A guest add-to-cart flow (client-side
storage synced to the server on login) is real, non-trivial frontend
work belonging to a later storefront-UI phase, not silently assumed
here.

**No frontend login/logout UI exists yet** (Phase 3 only built the
backend auth endpoints) — so `useCartStore`'s `reset()` (clearing cart
state so one user's data is never shown to the next) is implemented and
ready, but not yet wired to an actual logout button, since none exists
to wire it to. Whatever future login/logout flow is built should call
`useCartStore.getState().reset()`.

### Tests

82 new test methods (57 cart, 25 wishlist — 207 total across the whole
project as of this phase) across `apps/cart/tests/` (`test_authentication.py`,
`test_ownership.py`, `test_add.py`, `test_update.py`,
`test_remove_and_clear.py`, `test_pricing.py`, `test_performance.py`)
and `apps/wishlist/tests/` (`test_wishlist.py`, `test_performance.py`),
including regression tests for all three bugs above, the NULL-variant
constraint interaction, and N+1 guards using the same query-count-across-
different-sizes methodology established in Phase 4.

---

## What Phase 6 built

Phase 6 (Checkout and Orders) converts a cart (Phase 5) into a real,
persisted `Order`/`OrderItem` using Phase 2's existing schema. **No
model or migration changes were needed or made** — confirmed by diffing
`apps/orders/models.py` byte-for-byte against the approved Phase 5
archive and by the migration count staying at 13.

### Endpoints

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/v1/orders/checkout/` | Convert the current cart into an Order |
| GET | `/api/v1/orders/` | The current user's order history (paginated, newest first) |
| GET | `/api/v1/orders/{id}/` | A single order — ownership-scoped |

All three require authentication (session + CSRF, unchanged). There is
no write endpoint for orders beyond checkout itself — status changes are
a Django Admin / future-phase concern, not customer-writable.

### Checkout is server-authoritative by construction, not by convention

`CheckoutSerializer` (the only input checkout accepts) carries **only an
address selection** — `address_id` or inline address fields. No price,
quantity, discount, shipping cost, or total field exists anywhere in
that input shape, so there is nothing for a malicious or buggy client
payload to override even if it tried (asserted directly:
`test_client_supplied_price_fields_are_ignored` sends fake
`subtotal`/`total`/`shipping_cost` values in the request body and
confirms they're silently ignored). Every monetary value on the created
Order comes from `apps.cart.services.build_cart_view()` — the exact
same live-pricing mechanism Phase 5's cart uses, itself built on Phase
4's `apps.products.pricing` — computed fresh at the moment of checkout,
never trusted from anywhere else.

### Shipping: a real abstraction, not inline arithmetic

`apps/orders/shipping.py` is the one place shipping cost is computed —
a configurable flat rate (`STANDARD_SHIPPING_COST`) that becomes free at
or above a configurable threshold (`FREE_SHIPPING_THRESHOLD`), both set
via environment variables (see `.env.example`), never hardcoded. This is
deliberately a single method, not a speculative multi-carrier system —
nothing in the master spec asks for selectable carriers, and the
function signature (`subtotal` in, cost out) is the only thing checkout
code depends on, so swapping the internals for a real carrier/zone-based
system later requires changing only this one module.

### What's explicitly NOT in Phase 6 (by design, not oversight)

Per this phase's own approved scope boundaries:
- **No stock decrement.** Checkout re-validates that current stock is
  sufficient (reusing the exact same availability check Phase 5's cart
  already performs), but does not reserve or subtract it — the master
  spec's own payment flow diagram (section 26-27) shows "Reduce
  Inventory" happening *after* "Mark Payment As Paid," which doesn't
  exist until Phase 7.
- **No coupon/discount application.** `Order.discount_amount` is always
  `0` and `Order.coupon` stays unset. The master spec doesn't assign
  coupon application to any specific numbered phase, and it wasn't
  requested for this one.
- **No payment gateway interaction whatsoever.** Every order created
  here starts at `Order.Status.PENDING` / `Order.PaymentStatus.UNPAID`
  and stays there — asserted directly in
  `test_checkout_starts_pending_and_unpaid`.

### Address handling: reuses Phase 3's `Address`, doesn't duplicate its validation

Checkout accepts either `address_id` (one of the caller's own saved
addresses — ownership-checked server-side, not just trusted from the
request) or a full inline address (a one-off address, not saved to the
account). The postal-code validation rule was **extracted** from
`apps.accounts.serializers.AddressSerializer` into
`apps/accounts/validators.py` so both `AddressSerializer` and
`CheckoutSerializer` share exactly one implementation instead of two
copies that could drift — a pure refactor verified to leave
`AddressSerializer`'s own behavior unchanged (same rule, same error
message).

### Snapshotting, verified by actually mutating the source afterward

`OrderItem` stores `product_name`/`sku`/`unit_price`/`total_price` as
flat copies, and `Order` stores `shipping_*` as flat copies too (both
established in Phase 2) — checkout populates every one of these at
creation time and never re-reads the source afterward. This is tested
by **actually changing the source data after checkout and re-fetching
the order**: `test_order_survives_later_price_change` changes the
product's price and confirms the order still shows the old one;
`test_order_survives_later_product_deletion` deletes the product
entirely and confirms the order still displays the snapshotted name/SKU
with `product_id: null`; `test_order_survives_later_address_edit` edits
the saved address and confirms the order's shipping city didn't move
with it.

### Transaction handling: locking where it's actually needed

`services.checkout()` wraps order creation in `transaction.atomic()`
and calls `cart.items.select_for_update()` before reading the cart —
this serializes a double-submit (the same cart checked out twice in
quick succession, e.g. an impatient double-click) so the second attempt
correctly sees an empty cart and is rejected, rather than both
succeeding and producing two orders from one cart's contents. Real
concurrent-thread testing is impractical inside Django's
transaction-wrapped `TestCase` machinery (see
`test_atomicity.py`'s module docstring for why) — what's tested instead
is deterministic and realistic without needing real threads: that a
rejected checkout leaves zero partial `Order`/`OrderItem` rows behind,
that a mid-checkout exception correctly rolls back everything already
written (verified by mocking `bulk_create` to raise and confirming no
`Order` row survives), and that two sequential checkouts of the same
cart produce exactly one order, not two.

### Ownership

`OrderListView`/`OrderDetailView` scope their queryset to
`Order.objects.filter(user=request.user)` — another user's order 404s
rather than 403ing (it doesn't exist from the requester's point of
view, same pattern used for addresses/cart items/wishlist items
throughout this project), and the response body of a 404 never leaks
any of the order's actual contents.

### N+1 avoidance

List and detail both use one `prefetch_related` for `items` (with
`select_related("product", "variant")` nested inside it) — a small,
fixed number of queries regardless of how many orders are listed or how
many items each contains. Verified via the same
query-count-across-different-sizes methodology established in Phase
4/5: `test_performance.py` compares 3 vs. 12 orders, 2 vs. 10 items per
order, and — the most important case — a checkout of a 2-item cart vs.
a 15-item cart, confirming query count doesn't scale with cart size at
the point where a customer actually completes a purchase.

### Frontend data layer

`frontend/src/services/orderApi.js` — `checkout()`, `fetchOrders()`,
`fetchOrder()`, verified field-for-field against the actual
`OrderSerializer`/`CheckoutSerializer` rather than assumed.
`frontend/src/hooks/useOrders.js` — `useOrders`/`useOrder` are plain
read hooks (order history doesn't need the cross-cutting global state a
cart badge does, same reasoning Phase 5 applied to wishlist);
`useCheckout` is the one piece that touches existing state: after a
successful checkout, it calls `useCartStore.getState().fetchCart()` so
the cart store reflects the server-side clearing that just happened,
rather than assuming the new (empty) shape locally. No visual checkout
pages were built, per this phase's own scope boundary — this is the
reusable data layer a later storefront-UI phase builds on.

**Minor DRY refactor along the way**: the `useAsync` loading/error state
machine, originally private to Phase 4's `useCatalog.js`, was extracted
into `frontend/src/hooks/useAsync.js` so `useOrders.js` could reuse it
instead of becoming a third near-identical copy. `useCatalog.js`'s own
exported behavior is unchanged — this is a pure extraction.

### Tests

43 new test methods (250 total across the whole project) across
`apps/orders/tests/` (`test_checkout.py`, `test_order_list_detail.py`,
`test_atomicity.py`, `test_performance.py`), covering: successful
checkout (inline and saved-address), pending/unpaid status, empty cart,
inactive product/variant, insufficient stock, partial-unavailability
(no partial orders), address ownership/validation, shipping calculation
and the free-shipping threshold boundary, server-authoritative pricing
with a client-supplied-price-is-ignored regression test, sale-price
propagation into order totals, all three snapshot-survival tests
described above, order list/detail ownership (including the
guess-another-user's-ID case), pagination, and the query-count N+1
guards.

---

## What Phase 7 will build

Per the original phase plan: **Payment architecture** — a real payment
gateway integration (credentials to be provided separately, per the
master spec's explicit instruction not to invent them), payment
verification, transitioning `Order.payment_status` from `unpaid` to
`paid`, and — only once payment is confirmed — the inventory decrement
this phase deliberately deferred (per the master spec's own payment flow
diagram). Coupon application, reviews, banners, daily deals, and the
final storefront UI remain later-phase work.

No further phase will begin until you explicitly ask for it.
