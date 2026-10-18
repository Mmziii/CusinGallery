# PROGRESS — Prompt 1 (header, menus, home page)

Branch: `arena/f3669eb3-cusingallery` (off `main` @ 781ca78, PR #9 merged).

## Stage checklist

- [x] Stage 1 — Root category "آشپزخانه" + breadcrumbs starting with "کازین گالری" (migration 0006 + tests; helpers in utils/categories.js; breadcrumbs + JSON-LD on shop/product pages)
- [ ] Stage 2 — Header "دسته‌بندی کالاها" mega menu (Digikala style)
- [ ] Stage 3 — Hamburger (☰) menu: simple and animated
- [ ] Stage 4 — Trust strip under the home banner
- [ ] Stage 5 — "پیشنهاد امروز" (daily deal) card
- [ ] Stage 6 — Persian digits cleanup (storefront only)
- [ ] Stage 7 — Final checks

## Notes

- Baseline (before any change): backend suite passes on SQLite (`DATABASE_URL=sqlite:///…`);
  vitest: 375 passed, **2 pre-existing failures** in `src/admin-theme/menu.test.js`
  ("per-user sidebar group persistence") — admin-theme, out of scope for this prompt;
  verified failing on clean `main` checkout.

## Notes (stage 1)

- Migration `0006_kitchen_root_category` is idempotent (skips when a root with slug `kitchen` exists) and reversible (children back to top level, root deleted; deactivated instead if something was attached directly).
- `seed_demo` now nests the 4 main groups under the kitchen root for fresh installs.
- `CategoryMiniSerializer` gained an `ancestors` field (top-most first) so the product page renders the full trail without a second request.
- Frontend helpers live in `frontend/src/utils/categories.js` (`mainGroups`, `categoryUrl`, `categoryChain`, `KITCHEN_ROOT_SLUG`); header mega menu, home tiles and the shop category select now use them (select excludes the product-less root).
- Two existing category tests needed updates (they assumed no migrated root): the list test now asserts membership, and two tree tests no longer use slug "kitchen" for their own fixture roots.

## Not done

(nothing yet)

## Report

(final report will be added here at the end)
