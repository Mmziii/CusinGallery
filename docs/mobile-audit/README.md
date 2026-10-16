# Mobile audit 19 — report

The owner tested the live site on a 375px phone and reported six problems.
This is the record of what changed, how each item was solved and what could
not be verified from inside the repository.

Brand look (dark olive header, gold accents, Vazirmatn) is untouched: no new
palette, no new font, no new npm package.

---

## 1. Mobile product grid (the big one)

**Symptoms.** One product per row (350–550px tall cards), so 40 products were
~16 screens of scrolling; a filter block above the products; page-number
paging; and the phone header was crowded.

**What changed**

| Surface | Phone (≤767px) | Tablet (768–1023px) | Desktop (≥1024px) |
|---|---|---|---|
| `.product-grid`, `.related-grid`, `.wishlist-grid`, `.complements__grid` | 2 columns, 8px gap | 3 columns | unchanged |
| page padding (`.container`) | 12px | unchanged | unchanged |
| card | compact card (below) | unchanged | unchanged |
| home deals rail | horizontal, cards at **44%** of the viewport width | unchanged | unchanged |
| `/shop` toolbar | sticky bar under the header: «فیلترها» + «مرتب‌سازی» + «۴۰ کالا» | unchanged | unchanged |
| `/shop` paging | «نمایش کالاهای بیشتر» (walks the same `?page=` URLs) | unchanged | numbered links |

* **Compact card** (`frontend/src/components/ProductCard.jsx`, compact branch):
  square image (`aspect-ratio: 1/1`, `object-fit: contain`, light `#f3f1e8`
  field), badges as small chips in one corner, wishlist heart in the *opposite*
  corner (32px), 2-line name (13px), 1-line brand line (11px, its space
  reserved with `&nbsp;` when the product has none), and a bottom row holding
  the crossed-out old price + the bold final price (so prices line up across a
  row) and the round cart-plus button (36px). Out-of-stock items show
  «موجود شد خبرم کن» as a small text link instead of the button.
* Adding on a phone toasts the short «به سبد اضافه شد» with the «مشاهده سبد»
  action; desktop keeps its longer wording.
* **Filters/sorting sheets** (`frontend/src/pages/ShopPage.jsx` + `.sheet`
  CSS): the phone gets bottom sheets (portaled, focus-trapped, Escape closes,
  scrim, `اعمال` button, active-filter count on the button and in the
  heading). The long sidebar block is not rendered on a phone at all.
* **Skeletons:** the shop's first paint is a 6-card skeleton grid using the
  same 2-column grid (and the shared card skeleton now has a square media box
  at every width), so nothing shifts when products and images arrive.
* **Sticky containment:** the bar lives inside `.shop__main` — a grid item's
  sticky travel box is its own row, so the bar would never have moved
  otherwise. `--site-header-height` (measured by the header, `ResizeObserver` +
  scroll + resize) keeps it glued right under the header even when the phone
  layout wraps the search onto a second row.

**Files:** `frontend/src/components/ProductCard.jsx`,
`frontend/src/pages/ShopPage.jsx`, `frontend/src/components/Header.jsx`,
`frontend/src/components/Icon.jsx` (cart-plus), `frontend/src/styles/storefront.css`.

**Tests:** `frontend/src/components/ProductCard.compact.test.jsx`,
`frontend/src/pages/ShopPage.mobile.test.jsx`,
`e2e/mobile-grid.spec.js` (real 375px geometry, 320/360/375/390/414px overflow
sweep).

## 2. Mobile checkout

* On phones the checkout is a real step flow driven by the existing stepper:
  address → **delivery method** → review → payment. One step is visible at a
  time (`hidden` on the others), earlier steps are clickable buttons on the
  stepper, and a step cannot be left while its own validation fails (the same
  `collectIssues()` rules the submit path uses; the cart is never touched).
* A fixed bottom bar carries the current step's main button («ادامه: انتخاب
  روش ارسال» / «ادامه: بازبینی» / «ثبت سفارش»), the payable amount and the
  first blocking message.
* Delivery options are large selectable cards: icon (truck / bolt / store),
  title, delivery window, price or «رایگان», with the selected card clearly
  highlighted (gold border + tinted field + inner ring).
* The «بازبینی» step summarises the address, the delivery method (with a
  «تغییر» link back to that step) and the items, with the totals; the coupon
  input stays on that step and still works.
* Desktop keeps the single-page layout; the delivery section already followed
  the address directly and its heading is now unmistakably larger.

**Files:** `frontend/src/pages/CheckoutPage.jsx`,
`frontend/src/styles/storefront.css`.

**Tests:** `frontend/src/pages/CheckoutPage.mobile.test.jsx`; the existing
`CheckoutPage.placeorder.test.jsx` and `App.address-checkout.flow.test.jsx`
still pass unchanged (desktop path).

## 3. Password visibility toggle

* New `frontend/src/components/PasswordInput.jsx` (eye button *inside* the
  field, at the inline end = the left side in RTL, 40px tap target,
  `type="button"`, `aria-label` «نمایش رمز»/«پنهان کردن رمز», `aria-pressed`,
  eye/eye-off from the shared icon set). Used by the login page, the register
  page, the reset-confirm page and the account's change-password form — a
  guard test fails if any page hand-rolls a `type="password"` input again.
* Admin: new `backend/templates/admin/login.html` renders the same control as
  markup (Persian labels, sprite icons, `aria-controls`), and
  `initPasswordToggles()` in `admin_theme/js/theme.js` enhances every other
  password input of the panel (password change, reset confirm, user change
  form). Styling lives in `admin_theme/css/theme.css` (light theme, olive
  hover), both eye symbols were added to the admin sprite.

**Tests:** `frontend/src/components/PasswordInput.test.jsx`,
`frontend/src/admin-theme/passwordToggle.test.js`,
`backend/apps/adminui/tests/test_admin_password_toggle.py`.

## 4. Mobile header search

The phone rule that should have wrapped the search onto its own row was being
defeated by a later, unconditional `.site-header__search { flex: 1; max-width:
460px }` (the same specificity, declared later in the file). The phone block at
the end of the stylesheet re-asserts `flex: 1 0 100%`, `max-width: none` and
`order: 3`, so the field now owns a full row under the logo row (≥ 70% of the
viewport; the Persian placeholder «جستجوی محصول…» is fully visible) while the
account/cart controls keep the first row.

**Files:** `frontend/src/styles/storefront.css`.
**Tests:** `e2e/mobile-grid.spec.js` («the header search gets its own full-width
row», measured in the browser).

## 5. Real 404 status

* New catch-all view `backend/apps/core/spa.py`, mounted LAST in
  `backend/config/urls.py`. It knows both the SPA's route table
  (frontend/src/App.jsx) and the database, and answers:
  * a known route → the built `index.html`, **200**;
  * `/products/<slug>/` → 200 only for an existing **active** slug;
  * `/shop/?category=<slug>` → 200 only for an existing active category;
  * anything else → the same Persian document with **404**, plus
    `<meta name="robots" content="noindex">` and an `X-Robots-Tag: noindex`
    header, and `no-store` so a 404 can never be cached as the shell.
* The shell is read from `SPA_INDEX_FILE` (if set), else the repository's
  `frontend/index.html` (development), else fetched once from `SPA_SHELL_URL`
  (compose: `http://frontend/index.html`, cached 30 s so a deploy is never
  stale), else a small built-in Persian page — the view never 500s and never
  returns a blank 200.
* `nginx/conf.d/cusin.conf`, `nginx/prod.d/cusin.conf` and
  `nginx/prod.d/00-bootstrap-http.conf.example`: page requests (`location /`,
  the product and shop locations for non-bots) now proxy to the backend, while
  `/assets/`, `/fonts/`, `/brand/`, the favicons and `/index.html` keep being
  served by the frontend container (with the repeated security headers and
  their cache lifetimes). All regexes stay quoted.
* `docker-compose.yml` / `docker-compose.prod.yml` pass `SPA_SHELL_URL` to the
  backend; `.env.example` documents `SPA_INDEX_FILE` / `SPA_SHELL_URL`;
  `docs/DEPLOY.md` gained a short Persian section describing the new decision
  table.

**Tests:** `backend/apps/core/test_spa_404.py` (200 vs 404, inactive products,
unknown categories, non-page prefixes, noindex, cache headers, no-shell
fallback, plus a guard that compares the Django route table with the real
App.jsx router), `backend/apps/core/test_nginx_configs.py` (page requests reach
the backend catch-all; the build output still comes from the frontend
container).

## 6. Admin order status select

On the change form the `وضعیت سفارش` select now offers only what will be
accepted: the order's current status plus the transitions the DAG allows *and*
the payment rule accepts. Transitions the DAG allows but payment forbids (for
an unpaid order: «تأیید شده») are rendered as **disabled** options carrying
their Persian reason in a `title`, and the field's help text explains the
greyed-out entries — nothing is silently missing. The quick-status menu (B3c)
keeps its own, already-correct behaviour, and the server-side rule in
`apps/orders/workflow.py` is untouched (a crafted POST is still refused).

**Files:** `backend/apps/orders/admin.py` (`OrderStatusSelect`,
`OrderAdminForm`).
**Tests:** `backend/apps/adminui/tests/test_order_status_choices.py`.

---

## Changed files

**New**

```
backend/apps/core/spa.py                              catch-all: 200 vs 404 for page URLs
backend/apps/core/test_spa_404.py
backend/apps/adminui/tests/test_order_status_choices.py
backend/apps/adminui/tests/test_admin_password_toggle.py
backend/templates/admin/login.html                    themed login page + eye button
frontend/src/components/PasswordInput.jsx             one reusable password field
frontend/src/components/PasswordInput.test.jsx
frontend/src/components/ProductCard.compact.test.jsx
frontend/src/pages/ShopPage.mobile.test.jsx
frontend/src/pages/CheckoutPage.mobile.test.jsx
frontend/src/admin-theme/passwordToggle.test.js
e2e/mobile-grid.spec.js                               real-browser 375px checks
docs/mobile-audit/README.md                           this report
```

**Modified**

```
frontend/src/components/ProductCard.jsx     compact phone card
frontend/src/components/Header.jsx          measured --site-header-height
frontend/src/components/Icon.jsx            cart-plus / eye / eye-off / store / bolt
frontend/src/pages/ShopPage.jsx             sticky bar, sheets, load more, skeletons
frontend/src/pages/CheckoutPage.jsx         phone step flow + review step
frontend/src/pages/LoginPage.jsx            uses PasswordInput
frontend/src/pages/RegisterPage.jsx         uses PasswordInput
frontend/src/pages/PasswordResetConfirmPage.jsx
frontend/src/pages/account/ProfilePage.jsx
frontend/src/pages/StickyLayout.test.jsx    audits the new sticky bar
frontend/src/styles/storefront.css          all phone rules, sheets, compact card
backend/apps/orders/admin.py                OrderStatusSelect / OrderAdminForm
backend/apps/core/test_nginx_configs.py     page requests must reach the catch-all
backend/config/urls.py                      mounts the catch-all last
backend/config/settings/base.py             SPA_INDEX_FILE / SPA_SHELL_URL
backend/apps/adminui/templates/adminui/_sprite.html   eye-off symbol
backend/static/admin_theme/js/theme.js      initPasswordToggles()
backend/static/admin_theme/css/theme.css    .cusin-password styles
nginx/conf.d/cusin.conf                     page routing + asset locations
nginx/prod.d/cusin.conf                     same
nginx/prod.d/00-bootstrap-http.conf.example same
docker-compose.yml / docker-compose.prod.yml   SPA_SHELL_URL for the backend
.env.example / backend/.env.example         documented the two new settings
docs/DEPLOY.md / docs/E2E.md                routing + how to run the new spec
```

---

## Verification

```sh
# backend (1620 tests)
cd backend
DJANGO_SETTINGS_MODULE=config.settings.testing DATABASE_URL=sqlite:///db.sqlite3 \
  python manage.py test

# frontend (377 vitest tests)
cd frontend && npm run lint && npm test
```

`src/admin-theme/menu.test.js` has two failures that already existed on the
base commit (checked before any change here); they are unrelated to this work.

## Not done / not verifiable from inside the repo

* **Playwright could not be executed here.** `e2e/mobile-grid.spec.js` is
  written and syntax-checked, but this environment has no browser and the
  Playwright CDN is not reachable, so the geometry assertions (2 cards per row,
  the 320–414px overflow sweep, the sticky bar, the checkout steps) have not
  been run against a live stack. Run it with a Chromium installed:
  `cd e2e && E2E_BASE_URL=... npx playwright test mobile-grid.spec.js --project=chromium`
  (add `E2E_EXPECT_REAL_404=1` when pointing at the composed stack).
* **A screenshot pass at 375px** was not possible for the same reason; the CSS
  contract is pinned by source/computed-style tests instead.
* **The admin toggle needs the theme** (`ADMIN_THEME_ENABLED=True`): with the
  theme switched off, the stock Django login page has no eye button, since the
  theme's JS/CSS are what draw and wire it.
* **Back-in-stock** remains a form on the product page (there is no separate
  list surface in the storefront); out-of-stock cards in every grid are the
  "back-in-stock lists" the brief refers to and they follow the compact card.
