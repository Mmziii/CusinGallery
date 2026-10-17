# PROGRESS — Prompt 1 (header, menus, home page)

Branch: `arena/f3669eb3-cusingallery` (off `main` @ 781ca78, PR #9 merged).

## Stage checklist

- [ ] Stage 1 — Root category "آشپزخانه" + breadcrumbs starting with "کازین گالری"
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

## Not done

(nothing yet)

## Report

(final report will be added here at the end)
