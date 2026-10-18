# PROGRESS — Prompt 1 (header, menus, home page)

Branch: `arena/f3669eb3-cusingallery` (off `main` @ 781ca78, PR #9 merged).

## Stage checklist

- [x] Stage 1 — Root category "آشپزخانه" + breadcrumbs starting with "کازین گالری" (migration 0006 + tests; helpers in utils/categories.js; breadcrumbs + JSON-LD on shop/product pages)
- [x] Stage 2 — Header "دسته‌بندی کالاها" mega menu (Digikala style) (MegaMenu.jsx: 150ms hover intent, 200ms close grace, columns panel + gold active line + overlay + 70vh scroll; mobile sheet with drill-down, بازگشت, مشاهدهٔ همه, scroll lock; arrow keys, aria, focus restore)
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

## Notes (stage 2)

- New `frontend/src/components/MegaMenu.jsx` owns the whole menu (desktop panel + mobile sheet); Header keeps only the open state so navigation still closes every surface.
- Desktop: hover opens after 150 ms intent (the old tests' `waitFor` accidentally relied on synchronous opening — they now assert inside `waitFor` so they wait for real); click/Enter opens immediately; close on 200 ms mouse-leave grace, Escape, outside click. Panel: roots column (icon+name, active = gold line on the right) + sub-category columns with bold «›» headings and a «همهٔ محصولات X ›» link on top; 70vh max-height with own scroll; dimmed overlay; fade+8px slide-down on open (200 ms ease-out; global reduced-motion rule covers it).
- Sub-categories with no active products anywhere in their subtree are pruned (`pruneEmptyCategories` in utils/categories.js); nodes without a `product_count` (older payloads/test fixtures) are assumed non-empty.
- The trigger moved out of `.site-header__nav` (which phones hide) so «دسته‌بندی کالاها» finally shows on phones; under 1024px the button opens a full-height sheet (250 ms slide from the right) with drill-down («بازگشت» + title, «مشاهدهٔ همه» on every level), body scroll lock and a focus trap. The two surfaces are separated by CSS media queries, so hover stays attached on touch laptops.
- Playwright browsers cannot download in this sandbox (cdn.playwright.dev is outside the network allowlist) — the e2e spec for stage 7 is delivered as code and noted in the report.

## Not done

(nothing yet)

## Report

(final report will be added here at the end)
