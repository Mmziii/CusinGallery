# Live storefront audit

The nineteen numbered commits correspond to the nineteen requested fixes.
Palette tokens and Vazirmatn fonts are retained. New motion has explicit
`prefers-reduced-motion: reduce` overrides.

## Verification

After **each** numbered item:

```sh
cd frontend && npm test
cd ../backend
DJANGO_SETTINGS_MODULE=config.settings.testing DATABASE_URL=sqlite:///db.sqlite3 python manage.py test --noinput
```

`testing.py` uses Django's fast MD5 password hasher **only for tests**; runtime
settings keep their original secure password hashers. Two existing backend
stock-privacy assertions were updated because the new stock caps require the
API to expose stock. Existing English-message, phone, and Latin display-digit
expectations were updated to the requested behavior.

Final checks also include frontend lint/build and real Chromium geometry tests:

```sh
cd e2e
E2E_BASE_URL=http://localhost:5173 npm test -- storefront-overflow --project=chromium
```

The browser suite registers a disposable local customer, adds a real catalog
product to the cart, and checks home, shop, product, cart, checkout and account
at **360, 390, 768, 1280, 1366 and 1920 CSS pixels**. It checks visible text's
horizontal and vertical overflow, intentional line clamps/ellipsis excluded.
It also checks equal card name/brand heights, aligned prices, computed header
and limited-stock contrast, and reduced-motion route animation. This verifies
responsive browser geometry, not a physical Windows 125%/150% desktop session.

Backend: **1,194 tests, 2 skipped** (existing skips). Frontend: **338 tests**. Chromium acceptance: **3 tests**. New focused tests cover stock-limit rollback/caps, normalized mobiles,
Persian price input, missing products, card alignment, viewport overflow,
display digits/dates/delivery ranges, address formatting and combobox keyboard
interaction.

## Screenshot comparisons

`before/` was captured against commit `9f56b85` (before visual work, items 7–11)
served from a separate archived frontend, without switching the working branch.
`after/` uses the final working tree. Both use the same local demo catalog,
1366×900 desktop viewport; picker mobile screenshots use 390×844. Local demo
accounts and database are not included in Git. Full-page screenshots preserve
the entire layout; static images cannot demonstrate the timing of animations.

| Item | Before | After |
| --- | --- | --- |
| 7 — equal card rhythm | [shop](before/shop.png) | [shop](after/shop.png) |
| 8 — modest type/padding scale | [home](before/home.png), [product](before/product.png) | [home](after/home.png), [product](after/product.png) |
| 9 — loading transition | [spinner](before/loading.png) | [skeleton](after/loading.png) |
| 10 — wishlist feedback | [empty hearts](before/wishlist-feedback.png) | [filled heart, count and toast](after/wishlist-feedback.png) |
| 11 — searchable location picker | [desktop](before/address-picker.png), [mobile](before/address-picker-mobile.png) | [desktop](after/address-picker.png), [mobile sheet](after/address-picker-mobile.png) |

The checkout pickup details are rendered only when configured in site settings.
The restock confirmation intentionally promises no SMS delivery; delivery still
depends on the deployment's notification-provider configuration.
