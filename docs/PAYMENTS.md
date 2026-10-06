# Payments — developer guide

Phase C state of `apps/payments` + the money side of `apps/orders`:
a real ZarinPal integration (sandbox **and** production), a
gateway-registry design where a new PSP is one adapter class, verified /
idempotent / race-safe callbacks, refund bookkeeping for manual PSP
refunds, and a cron-safe abandoned-order expiry command.

The owner-facing manual (how to see paid orders, how to process a
refund-required order) lives in `docs/OWNER_GUIDE.fa.md` §۸.

---

## 1. Architecture in one picture

```
customer browser            Django backend                     ZarinPal
─────────────────    ─────────────────────────────────    ─────────────────────
POST /payments/initiate/ ─▶ services.initiate_payment
                             ├─ Payment row (PENDING,
                             │   amount = order.total snapshot)
                             ├─ order.payment_status = pending
                             └─ gateway.initiate() ─────────▶ POST /pg/v4/payment/request.json
                              redirect_url ◀──────────────────  {authority}
browser ── redirect ─────────────────────────────────────▶  /pg/StartPay/{authority}
                                                             (hosted payment page)
GET /payment/callback/?Authority=…&Status=OK|NOK ◀───────── browser sent back
                             services.handle_callback
                             ├─ look up attempt by GATEWAY reference
                             ├─ terminal? → return unchanged (idempotent)
                             ├─ gateway.verify() ───────────▶ POST /pg/v4/payment/verify.json
                             │    (server-to-server; the      {code, ref_id, card_pan, card_hash}
                             │     callback query is NEVER
                             │     trusted on its own)
                             └─ under payment+order row locks:
                                  SUCCESS  → order paid+confirmed, stock −1×, coupon usage
                                  FAILED   → order payment_status failed
                                  CANCELLED→ order back to unpaid
                                  (GatewayError during verify → stays PENDING on purpose)
                             302 → frontend /payment/result/{id}/?status=…
```

Key modules (each is the *only* home of its logic):

| File | Responsibility |
|---|---|
| `apps/payments/gateways/base.py` | `PaymentGateway` ABC, `InitiateResult`, `VerificationResult`, `GatewayError` |
| `apps/payments/gateways/zarinpal.py` | the real ZarinPal v4 adapter (sandbox + production) |
| `apps/payments/gateways/mock.py` | dev/test gateway with HMAC-signed callbacks |
| `apps/payments/gateways/__init__.py` | `_REGISTRY` + `get_gateway()` (env-selected) |
| `apps/payments/services.py` | initiate/callback state machine, locks, idempotency, amount cross-check |
| `apps/orders/inventory.py` | the only place stock moves |
| `apps/orders/refunds.py` | the only place refund ledger fields are written |
| `apps/orders/workflow.py` | the only order-status state machine (flags refunds on cancel/return) |
| `apps/orders/management/commands/expire_unpaid_orders.py` | cron cleanup of abandoned unpaid orders |

## 2. Environment variables

All configuration is env-only (documented identically in **root
`.env.example`** and **`backend/.env.example`**); nothing is hardcoded
and no secret ever reaches the browser.

| Variable | Values / example | Purpose |
|---|---|---|
| `PAYMENT_GATEWAY` | `mock` \| `zarinpal` | Selects the adapter via the registry. Empty ⇒ `mock`. **Production settings refuse to boot with `mock`/empty.** |
| `PAYMENT_MERCHANT_ID` | `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx` | ZarinPal 36-char merchant id (from the merchant panel). Required for `zarinpal` in production (boot guard). The mock gateway uses this slot as its HMAC signing secret (falls back to `SECRET_KEY`). |
| `PAYMENT_ZARINPAL_SANDBOX` | `True` / `False` | `True` → all ZarinPal calls go to `sandbox.zarinpal.com` (test mode, any 36-char merchant id, no real money). `False` → `api.zarinpal.com` + `www.zarinpal.com`. |
| `PAYMENT_CALLBACK_URL` | `https://cusin.ir/payment/callback/` | Fallback callback base URL. When payments are initiated through the API view, the URL is built from the incoming request instead (correct on any origin); this value is what you register in the ZarinPal panel. The shipped nginx config proxies `/payment/callback/` to Django (exact prefix — the SPA's `/payment/result/` pages keep going to the frontend). |
| `PAYMENT_GATEWAY_TIMEOUT` | `15` (seconds) | Per-call HTTP timeout for request/verify. Exceeding it is treated as “gateway unreachable” (`GatewayError`). |
| `ORDER_EXPIRY_HOURS` | `24` | Default age threshold for `expire_unpaid_orders`. |

## 3. ZarinPal specifics the adapter encodes

* **v4 REST API**, JSON envelopes `{"data": {...}, "errors": {...}|[]}`.
* **Money unit:** whole **Toman** with `"currency": "IRT"` on *both*
  request and verify — no Rial conversion exists anywhere in the code
  (the project stores whole-Toman integers by design).
* **Endpoints:** `…/pg/v4/payment/request.json`, `…/pg/v4/payment/verify.json`,
  customer redirect `…/pg/StartPay/{authority}` — hosts differ between
  sandbox and production, nothing else does.
* **Callback:** ZarinPal appends `?Authority=…&Status=OK|NOK` to the
  callback URL. `Status` only *routes* the logic; it never decides it.
  `NOK` (failed **or** customer-cancelled — ZarinPal does not
  distinguish) is recorded as `cancelled` without calling verify, per
  ZarinPal's own instruction. `OK` triggers the server-side verify.
* **Verify codes:** `100` = captured now; `101` = “already verified
  once” (ZarinPal's documented idempotent repeat-verify answer — still a
  successful capture, which is what makes replayed callbacks and
  lost-response retries resolve correctly). Anything else / an `errors`
  envelope = definitive non-success.
* **Receipt data:** on success the adapter passes through `ref_id`
  (stored as `Payment.gateway_ref_id`), `card_pan` (masked, e.g.
  `603770******4281`) and `card_hash` (SHA-256 fingerprint →
  `Payment.card_pan_hash`). No full PAN ever reaches this project.
* **Error split:** network/HTTP/JSON problems raise `GatewayError`;
  business refusals inside a well-formed response are ordinary results.
  On **initiate**, `GatewayError` ⇒ attempt FAILED + HTTP 502 to the
  client. On **verify**, `GatewayError` ⇒ attempt **stays PENDING**
  (money state unknown — never mark FAILED just because *our* call
  failed, never mark SUCCESS without the gateway's answer) and the
  customer sees the result page's “pending / در حال بررسی” state.

## 4. Security & correctness invariants

1. **Server-side verification of every callback.** The redirect query is
   used only to *find* the attempt (by the gateway's own transaction
   reference — `Authority` for ZarinPal; see
   `services.GATEWAY_REFERENCE_KEYS`). The outcome comes exclusively from
   `gateway.verify()` (real PSP re-check) or the mock's HMAC validation.
2. **Amount cross-check, twice.** Verify sends the *snapshot* amount
   taken at initiation (`payment.amount`), so the PSP itself confirms the
   money matches what the customer was charged; then
   `_complete_successful_payment` refuses the paid transition unless
   `payment.amount == order.total` (post-checkout order edits ⇒ FAILED,
   loud log).
3. **Idempotent callbacks.** Terminal attempts (SUCCESS/FAILED/
   CANCELLED) are returned unchanged — replays never double-pay, never
   double-decrement stock, never even reach the gateway again.
4. **Simultaneous callbacks.** `select_for_update` on the payment row
   *and* the order row serializes concurrent callbacks (including two
   different attempts of one order); the partial unique constraint
   `unique_successful_payment_per_order` is the final database-level
   backstop (IntegrityError is caught and resolved as “already paid”).
5. **Verified money is never lost.** If a capture verifies for an order
   that can no longer receive it — already cancelled/returned (expiry
   race) or already paid by another attempt (double charge) — the
   payment/ledger records it and the order is flagged **refund required**
   (`apps/orders/refunds.py`) with the exact amount and a journal note.
6. **Stock moves exactly once**, only inside the PENDING→SUCCESS
   transition (`apps/orders/inventory.py`), never at checkout, never for
   unpaid/expired orders.
7. **Production cannot run the mock gateway.**
   `config/settings/production.py` raises at boot for
   `PAYMENT_GATEWAY=mock`/empty, and for `zarinpal` without a merchant
   id — the same fail-closed style as the `SECRET_KEY`/CORS guards.

### Status transitions

```
Payment:  PENDING ─▶ SUCCESS | FAILED | CANCELLED        (terminal; no way back)
          PENDING ─▶ PENDING                              (verify unreachable — retryable)

Order.payment_status:
          unpaid ─▶ pending (initiate) ─▶ paid (success) ─▶ refunded (owner marks refund)
                          │
                          ├─▶ unpaid   (customer cancelled at the gateway)
                          └─▶ failed   (gateway declined / verification failed /
                                        amount mismatch — retryable: a new attempt
                                        starts from here)
```

## 5. Refund tracking (manual refunds)

There is **no automatic refund integration** — Iranian PSP refunds are
executed by the owner in the ZarinPal merchant panel. The system's job
is bookkeeping, and all of it flows through `apps/orders/refunds.py`:

* `Order.refund_status` — `none` / `required` (نیازمند بازپرداخت) /
  `refunded` (بازپرداخت شده), `Order.refund_amount` (Toman,
  **accumulates** across events), `Order.refund_reference` (append-only
  journal), `Order.refunded_at` (system-stamped).
* Flagged automatically when: a **paid** order is cancelled or returned
  (`workflow.set_status`); a verified capture lands on a
  cancelled/returned order; a duplicate second capture verifies.
* Completed by the owner in Django admin: refund fieldset on the order
  page — moving `refund_status` to «بازپرداخت شده» **requires an added
  note/reference**, stamps `refunded_at`, and moves `payment_status`
  `paid → refunded`. Invalid ledger moves persist nothing. The
  `refund_status` list filter (and the 💸 badge) is the daily “who is
  owed money?” view.

## 6. Abandoned orders: `expire_unpaid_orders`

```bash
python manage.py expire_unpaid_orders            # default: ORDER_EXPIRY_HOURS (24)
python manage.py expire_unpaid_orders --hours 6  # per-run override
python manage.py expire_unpaid_orders --dry-run  # list only, change nothing
```

Cancels `status=pending` orders with `payment_status ∈ {unpaid, pending,
failed}` older than the cutoff. Cron-safe: narrow selection, each
candidate **re-checked under its row lock** before cancelling (an order
paid mid-run is skipped), cancels go through `workflow.set_status` (so
no stock moves — unpaid orders never reserved any — and no refund is
flagged), immediate re-runs find nothing. Suggested cron (host crontab,
hourly):

```cron
0 * * * * cd /path/to/deploy && docker compose exec -T backend python manage.py expire_unpaid_orders >> /var/log/cusin-expire.log 2>&1
```

If a customer nonetheless pays an expired order (they were already on
the gateway page), the callback records the verified capture and flags
the order refund-required — see §4.5. Stale PENDING payment attempts are
deliberately left PENDING so that path keeps working.

## 7. Adding another gateway (IDPay, NextPay, …)

Exactly one new class + one registry line — nothing else changes:

1. Create `apps/payments/gateways/<name>.py` subclassing
   `PaymentGateway`:
   * `name = "<name>"` (the `PAYMENT_GATEWAY` value),
   * `initiate(payment, callback_url) -> InitiateResult` — register the
     payment with the PSP, return its transaction handle + the customer
     redirect URL. Raise `GatewayError` for unreachable/refused. Read
     credentials from `settings` (add env vars in
     `config/settings/base.py` + **both** `.env.example` files),
   * `verify(payment, callback_data) -> VerificationResult` — decide the
     outcome **server-side** (re-ask the PSP; never trust the query
     string). Return `cancelled=True` for customer-cancel outcomes,
     raise `GatewayError` only when the PSP itself can't be reached.
     Pass through `gateway_ref_id` / `card_pan` (masked) /
     `card_fingerprint` if the PSP returns them.
   * If the PSP's callback reference parameter isn't already in
     `services.GATEWAY_REFERENCE_KEYS` (e.g. IDPay's `idpay_trxid`), add
     that key there.
2. Register in `apps/payments/gateways/__init__.py`:
   `_REGISTRY[<Name>Gateway.name] = <Name>Gateway`.
3. If it must be usable in production, nothing else is needed — the
   production boot guard only bans `mock`.
4. Add tests mirroring `apps/payments/tests/test_zarinpal.py` (fake HTTP
   layer, no network).

## 8. Testing policy

* **No test ever touches the network.** `test_zarinpal.py` patches
  `requests.post` at the adapter's call site (`FakeZarinpalHTTP`) and
  asserts both directions: the exact URLs/payloads that *would* be sent
  (Toman amounts, `currency=IRT`, stored authority — never
  callback-supplied values) and the handling of every response shape
  (100/101, `errors`, timeouts, HTTP 500, non-JSON).
* Covered behaviours: success (incl. receipt/card capture + exactly-once
  stock), user-cancelled (`Status=NOK`, no verify call), failed
  verification, amount mismatch despite gateway “OK”, replayed callback,
  **simultaneous callbacks** (threaded, PostgreSQL-only — skipped on
  SQLite with a documented reason), gateway timeout/unreachable on both
  initiate (⇒ 502 + FAILED) and verify (⇒ stays PENDING, then a replay
  completes it via code 101), registry selection, production boot
  guards, refund ledger (all triggers + admin paths + races), and
  unpaid-order expiry (incl. the pay-after-expiry money path).
* The mock gateway remains the flow-level test double for the rest of
  the suite (it implements the same protocol with real HMAC signing).

### Sandbox → production runbook

1. **Sandbox first** (works before the real merchant id exists):
   `PAYMENT_GATEWAY=zarinpal`, `PAYMENT_ZARINPAL_SANDBOX=True`,
   `PAYMENT_MERCHANT_ID=<any 36-char value>`, `PAYMENT_CALLBACK_URL`
   pointing at a publicly reachable backend (tunnel or staging —
   ZarinPal's sandbox redirects the *browser*, so localhost alone only
   works with a tunnel). Walk a full order: initiate → sandbox payment
   page → callback → result page → admin payment/order records.
2. **Go live:** register `cusin.ir` (and the exact callback URL) in the
   ZarinPal merchant panel, set `PAYMENT_MERCHANT_ID` to the real id,
   `PAYMENT_ZARINPAL_SANDBOX=False`, restart the backend. Production
   settings refuse to boot with the mock gateway or without a merchant
   id, so a misconfigured deploy fails loudly instead of silently
   “working” on a test gateway.
3. Enable the expiry cron (§6) and check the admin refund filter (§5)
   as part of the daily routine.

### Known limitation (honest status)

The adapter is verified against ZarinPal's documented v4 contract and a
fake HTTP layer in tests; it has **not** been exercised against the live
`sandbox.zarinpal.com` from this repository's development environment
(no outbound access to it here). Run the sandbox walk-through in step 1
on a machine that can reach ZarinPal before going live.
