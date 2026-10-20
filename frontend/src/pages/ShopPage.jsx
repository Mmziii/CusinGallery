import { faDigits } from "../utils/faDigits";
import PropTypes from "prop-types";
import { usePageMeta } from "../hooks/usePageMeta";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigationType, useSearchParams } from "react-router-dom";

import Breadcrumbs from "../components/Breadcrumbs";
import BrandFilter from "../components/BrandFilter";
import CategoryFilterTree from "../components/CategoryFilterTree";
import PriceRangeFilter from "../components/PriceRangeFilter";
import Icon from "../components/Icon";
import Portal from "../components/Portal";
import ProductCard from "../components/ProductCard";
import { ProductCardSkeleton } from "../components/Skeletons";
import { EmptyState, ErrorState } from "../components/ui";
import { useAsync } from "../hooks/useAsync";
import useFocusTrap from "../hooks/useFocusTrap";
import { useMediaQuery } from "../hooks/useMediaQuery";
import { listBrands, listCategories, listFacets, listProducts } from "../services/catalogApi";
import { errorMessage } from "../components/ui";
import { normalizeApiError } from "../utils/apiError";
import { trackEvent } from "../utils/behaviour";
import { formatPrice } from "../utils/formatPrice";
import { isTruthyParam } from "../utils/queryFlags";
import { shareImageUrl } from "../utils/shareImage";
import { brandShape } from "../utils/shapes";
import { brandUrl } from "../utils/brands";
import { categoryChain, categoryUrl } from "../utils/categories";

/** Part S5 item 7: max stagger steps (20ms each) for the card entrance. */
const MAX_STAGGER_STEPS = 10;

/**
 * Part S5 item 7: one collapsible filter group. The body animates with a
 * grid-template-rows 0fr -> 1fr transition (no max-height guesswork, so
 * any content height animates correctly) and stays in the DOM the whole
 * time -- inputs keep their state and the group stays keyboard-navigable.
 */
function FilterGroup({ title, children, defaultOpen = true }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className={`filter-group${open ? "" : " filter-group--collapsed"}`}>
      <h3>
        <button
          type="button"
          className="filter-group__toggle"
          aria-expanded={open}
          onClick={() => setOpen((value) => !value)}
        >
          <span>{title}</span>
          <Icon name="chevron-down" size={14} />
        </button>
      </h3>
      <div className="filter-group__body">
        <div className="filter-group__body-inner">{children}</div>
      </div>
    </div>
  );
}

FilterGroup.propTypes = {
  title: PropTypes.string.isRequired,
  children: PropTypes.node,
  defaultOpen: PropTypes.bool,
};

const SORT_OPTIONS = [
  { value: "newest", label: "جدیدترین" },
  { value: "oldest", label: "قدیمی‌ترین" },
  { value: "price_asc", label: "ارزان‌ترین" },
  { value: "price_desc", label: "گران‌ترین" },
];

/**
 * Catalog listing: search + category/brand/price/stock filters + sorting
 * + pagination, all reflected in the URL so views are shareable and the
 * back button behaves. Every param maps 1:1 to the backend's own filter
 * contract (apps/products/filters.py).
 */
function ShopPage({ brand: fixedBrand = null }) {
  const [searchParams, setSearchParams] = useSearchParams();
  // Part S5 item 7: on small screens the whole filter column collapses
  // into a drawer; the open/close transition is a grid-template-rows
  // 0fr -> 1fr animation (same technique as the filter groups).
  const [filtersOpen, setFiltersOpen] = useState(false);
  // Audit 19 item 1: phones get their own toolbar (sticky, under the header),
  // the filters and the sorting move into bottom sheets and page-number links
  // become a single «نمایش کالاهای بیشتر» button. The query matches the CSS
  // breakpoint exactly, so markup and stylesheet never disagree.
  const isMobile = useMediaQuery("(max-width: 767px)");
  const [sortOpen, setSortOpen] = useState(false);
  const filtersSheetRef = useRef(null);
  const sortSheetRef = useRef(null);
  const closeFilters = useCallback(() => setFiltersOpen(false), []);
  const closeSort = useCallback(() => setSortOpen(false), []);
  useFocusTrap(filtersSheetRef, isMobile && filtersOpen, closeFilters);
  useFocusTrap(sortSheetRef, isMobile && sortOpen, closeSort);

  const params = useMemo(() => {
    const p = {};
    for (const key of ["search", "category", "brand", "min_price", "max_price", "in_stock", "on_sale", "ordering", "page"]) {
      const value = searchParams.get(key);
      if (value) p[key] = value;
    }
    // Part R5 item 8: attribute facet filters live in attr_<attribute-slug>
    // params (comma-joined values) and are forwarded verbatim to the API.
    for (const key of searchParams.keys()) {
      const value = searchParams.get(key);
      if (key.startsWith("attr_") && value) p[key] = value;
    }
    // A brand URL is a fixed scope, not an optional query-string filter.
    if (fixedBrand) p.brand = fixedBrand.slug;
    return p;
  }, [searchParams, fixedBrand]);

  // The URL stays the single source of truth for paging (SEO + back button):
  // ?page=N means "the first N pages", so a deep link and the phone's
  // «نمایش کالاهای بیشتر» append the same way. Page 1 keeps the plain single
  // request it always had.
  const currentPage = Math.max(1, Number(params.page) || 1);
  const productsState = useAsync(async () => {
    if (currentPage <= 1) return listProducts(params);
    const pages = await Promise.all(
      Array.from({ length: currentPage }, (_, index) =>
        listProducts({ ...params, page: index + 1 })
      )
    );
    const last = pages[pages.length - 1];
    return { ...last, results: pages.flatMap((page) => page.results || []) };
  }, [searchParams.toString(), fixedBrand?.slug]);
  const categoriesState = useAsync(() => listCategories(), []);
  const brandsState = useAsync(() => listBrands(), []);
  // Facets re-scope whenever the selected category changes; the facet
  // counts then only cover that category's products.
  const facetsState = useAsync(
    () => listFacets({ ...(params.category ? { category: params.category } : {}), ...(params.brand ? { brand: params.brand } : {}) }),
    [params.category || "", params.brand || ""]
  );

  // Part S4 item 2: a category or brand page shares ITS OWN image (the
  // category image, or the brand tile with the brand logo as fallback) as
  // an absolute URL, and falls back to the shared brand placeholder when
  // that item has no image at all. An unfiltered /shop/ keeps the
  // site-wide og:image from index.html.
  const categories = useMemo(() => categoriesState.data?.results || [], [categoriesState.data]);
  const brands = brandsState.data?.results || [];
  const selectedCategory = categories.find((c) => c.slug === params.category) || null;
  // Stage 1: breadcrumbs walk the REAL tree (parent_slug chain,
  // top-most first) so a filtered shop shows
  // کازین گالری › آشپزخانه › <group> › … › <category>.
  const categoryCrumbs = useMemo(
    () =>
      categoryChain(params.category, categories).map((category) => ({
        label: faDigits(category.name),
        to: categoryUrl(category),
      })),
    [params.category, categories]
  );
  const selectedBrand = fixedBrand || brands.find((b) => b.slug === params.brand) || null;
  const filtered = fixedBrand || selectedCategory || selectedBrand;
  // Built by the shared helper (never by string concatenation): the
  // category image, the brand tile (or its logo), the placeholder.
  const listingShareImage = filtered
    ? shareImageUrl(fixedBrand ? fixedBrand.tile_image || fixedBrand.logo : selectedCategory ? selectedCategory.image : selectedBrand.tile_image || selectedBrand.logo)
    : undefined;
  usePageMeta({
    title: fixedBrand ? `محصولات برند ${faDigits(fixedBrand.name)}` : filtered ? faDigits(filtered.name) : "فروشگاه",
    path: fixedBrand ? brandUrl(fixedBrand.slug) : "/shop/",
    description:
      (fixedBrand ? `خرید محصولات برند ${faDigits(fixedBrand.name)} از کازین گالری؛ قیمت به تومان و ارسال به سراسر ایران.` : "") ||
      (selectedCategory && selectedCategory.description) ||
      (filtered
        ? `خرید آنلاین ${filtered.name} از کازین گالری؛ ارسال به سراسر ایران.`
        : "خرید آنلاین ظروف آشپزخانه، پخت‌وپز، بلور و کریستال و لوازم خانه با ارسال به سراسر ایران."),
    image: listingShareImage,
  });

  const setParam = (key, value) => {
    const next = new URLSearchParams(searchParams);
    if (value === "" || value === null || value === undefined) {
      next.delete(key);
    } else {
      next.set(key, value);
    }
    // Any filter change resets to the first page.
    if (key !== "page") next.delete("page");
    setSearchParams(next);
  };

  // Part R5 item 8: toggle one value inside attr_<attribute-slug>. Values
  // are comma-joined in the URL so a facet selection survives reload and
  // is shareable, exactly like every other filter.
  const selectedAttrValues = (attributeSlug) => {
    const raw = searchParams.get(`attr_${attributeSlug}`);
    return raw ? raw.split(",").filter(Boolean) : [];
  };
  const toggleAttrValue = (attributeSlug, value) => {
    const current = selectedAttrValues(attributeSlug);
    const next = current.includes(value)
      ? current.filter((v) => v !== value)
      : [...current, value];
    setParam(`attr_${attributeSlug}`, next.join(","));
  };

  const products = productsState.data;

  // Behaviour analytics: report each search query WITH its result count,
  // once the first page has loaded (the owner's «جستجوهای بی‌نتیجه»
  // report is built from exactly this pair). Fires once per query+count,
  // so paging or a re-render never inflates the numbers.
  const trackedSearch = useRef("");
  useEffect(() => {
    const query = (searchParams.get("search") || "").trim();
    if (!query || !products || typeof products.count !== "number") return;
    const stamp = `${query}|${products.count}`;
    if (trackedSearch.current === stamp) return;
    trackedSearch.current = stamp;
    trackEvent("search", { query, results: products.count });
  }, [searchParams, products]);
  const totalPages = products ? Math.ceil(products.count / 20) : 0;

  // Audit 19 item 1: how many filters are active right now -- shown on the
  // phone's «فیلترها» button and in the sheet heading, so a shopper always
  // knows why the list is short. Paging and sorting are not filters.
  const activeFilterCount =
    ["category", "brand", "min_price", "max_price", "in_stock"].filter((key) =>
      searchParams.get(key)
    ).length +
    [...searchParams.keys()].filter(
      (key) => key.startsWith("attr_") && searchParams.get(key)
    ).length;

  // Part S2 item 7: preserve scroll position when the browser navigates
  // BACK to this listing (filters already survive via the URL). The
  // position is stored per filter-set, so forward navigation starts fresh.
  const navigationType = useNavigationType();
  useEffect(() => {
    const key = `cusin.shop.scroll.${fixedBrand?.slug || ""}.${searchParams.toString()}`;
    if (navigationType === "POP") {
      const saved = sessionStorage.getItem(key);
      if (saved) {
        const y = Number(saved);
        requestAnimationFrame(() => window.scrollTo(0, y));
      }
    }
    return () => {
      sessionStorage.setItem(key, String(window.scrollY));
    };
  }, [searchParams, navigationType, fixedBrand?.slug]);

  // Part S5 item 7: a new result set re-triggers the staggered entrance
  // (the key remounts the cards -- their boxes are aspect-ratio sized, so
  // remounting cannot shift the layout).
  const [resultsKey, setResultsKey] = useState(0);
  useEffect(() => {
    if (productsState.data) setResultsKey((value) => value + 1);
  }, [productsState.data]);

  const applyPriceRange = ({ min, max }) => {
    const next = new URLSearchParams(searchParams);
    if (min == null) next.delete("min_price");
    else next.set("min_price", String(min));
    if (max == null) next.delete("max_price");
    else next.set("max_price", String(max));
    next.delete("page");
    setSearchParams(next);
  };

  const clearAllFilters = () => {
    const next = new URLSearchParams(searchParams);
    ["category", "brand", "min_price", "max_price", "in_stock", "on_sale", "page", ...attrKeys].forEach((k) => next.delete(k));
    setSearchParams(next);
  };

  // Attribute facet keys currently present in the URL (e.g. ["attr_rang"]).
  const attrKeys = [...searchParams.keys()].filter(
    (key) => key.startsWith("attr_") && searchParams.get(key)
  );

  // ONE filter panel, rendered either in the desktop sidebar or in the phone
  // bottom sheet -- never both, so no control (and no id) is ever duplicated.
  const filtersPanel = (
    <div className="shop__filters-inner">
      <FilterGroup title="دسته‌بندی">
        <CategoryFilterTree categories={categories} selected={params.category || ""} onChange={(value) => setParam("category", value)} />
      </FilterGroup>

      <FilterGroup title="برند">
        <BrandFilter brands={fixedBrand ? [fixedBrand] : brands} selected={params.brand || ""} locked={Boolean(fixedBrand)} onChange={(value) => setParam("brand", value)} />
      </FilterGroup>

      {/* Part R5 item 8: dynamic attribute facets, one checkbox group
          per attribute that exists on active products (re-scoped to
          the selected category). */}
      {(facetsState.data?.results || []).map((attribute) => {
        const selected = selectedAttrValues(attribute.slug);
        return (
          <FilterGroup key={attribute.slug} title={attribute.name}>
            {attribute.values.map((entry) => (
              <label className="checkbox" key={entry.value}>
                <input
                  type="checkbox"
                  checked={selected.includes(entry.value)}
                  onChange={() => toggleAttrValue(attribute.slug, entry.value)}
                />
                {faDigits(entry.value)} <span className="filter-group__count">({faDigits(entry.count)})</span>
              </label>
            ))}
          </FilterGroup>
        );
      })}

      <FilterGroup title="محدوده قیمت (تومان)">
        <PriceRangeFilter
          bounds={products?.price_bounds}
          resultRange={products?.price_range}
          minimum={params.min_price || ""}
          maximum={params.max_price || ""}
          onApply={applyPriceRange}
          scopeKey={`${fixedBrand?.slug || ""}|${searchParams.toString()}`}
        />
      </FilterGroup>

      <FilterGroup title="موجودی">
        <label className="checkbox">
          <input
            type="checkbox"
            checked={searchParams.get("in_stock") === "true"}
            onChange={(e) => setParam("in_stock", e.target.checked ? "true" : "")}
          />
          فقط کالاهای موجود
        </label>
      </FilterGroup>

      {/* The daily-deals band's «مشاهده همه» lands here: /shop/?on_sale=true
          (same filter the backend exposes, apps/products/filters.py, which
          also accepts 1/yes -- an old bookmark must still read as checked). */}
      <FilterGroup title="تخفیف">
        <label className="checkbox">
          <input
            type="checkbox"
            checked={isTruthyParam(searchParams.get("on_sale"))}
            onChange={(e) => setParam("on_sale", e.target.checked ? "true" : "")}
          />
          فقط کالاهای تخفیف‌دار
        </label>
      </FilterGroup>

      {(searchParams.get("category") || searchParams.get("brand") || searchParams.get("min_price") || searchParams.get("max_price") || searchParams.get("in_stock") || searchParams.get("on_sale") || attrKeys.length > 0) ? (
        <button type="button" className="btn btn--outline btn--sm" onClick={clearAllFilters}>
          حذف همه فیلترها
        </button>
      ) : null}
    </div>
  );

  return (
    <div className="shop">
      <div className="shop__heading">
        {/* Part S2 item 7: breadcrumbs (category chain once
            loaded). Stage 1: every storefront trail starts with
            «کازین گالری», then «آشپزخانه», then the deeper
            levels. */}
        <Breadcrumbs
          items={[
            { label: "کازین گالری", to: "/" },
            ...(fixedBrand
              ? [{ label: "برندها" }, { label: faDigits(fixedBrand.name) }]
              : params.category
              ? [{ label: "فروشگاه", to: "/shop/" }, ...categoryCrumbs]
              : [{ label: "فروشگاه" }]),
          ]}
        />
        <h1>{fixedBrand ? `محصولات برند ${faDigits(fixedBrand.name)}` : "فروشگاه"}</h1>
      </div>
      {isMobile ? null : (
        <aside className="shop__sidebar">
          {/* Part S5 item 7: on small screens the filter column folds into a
              drawer; the open/close motion is the same grid-template-rows
              0fr -> 1fr transition the groups use. The panel stays in the
              DOM, so nothing is lost when it is closed. On phones (Audit 19
              item 1) this whole block is REPLACED by the sticky toolbar and
              the bottom sheets below. */}
          <button
            type="button"
            className="shop__filters-toggle"
            aria-expanded={filtersOpen}
            aria-controls="shop-filters"
            onClick={() => setFiltersOpen((value) => !value)}
          >
            <span>فیلترها</span>
            <Icon name="chevron-down" size={16} />
          </button>

          <div
            className={`shop__filters${filtersOpen ? " shop__filters--open" : ""}`}
            id="shop-filters"
          >
            {filtersPanel}
          </div>
        </aside>
      )}

      {isMobile ? (
        <>
          {filtersOpen ? (
            <Portal>
              <button
                type="button"
                className="sheet-scrim"
                aria-label="بستن فیلترها"
                onClick={closeFilters}
              />
              <div
                className="sheet"
                id="shop-filters-sheet"
                role="dialog"
                aria-modal="true"
                aria-label="فیلترها"
                ref={filtersSheetRef}
              >
                <div className="sheet__head">
                  <h2>
                    فیلترها
                    {activeFilterCount > 0 ? ` (${formatPrice(activeFilterCount)})` : ""}
                  </h2>
                  <button
                    type="button"
                    className="sheet__close"
                    aria-label="بستن"
                    onClick={closeFilters}
                  >
                    <Icon name="close" size={16} />
                  </button>
                </div>
                <div className="sheet__body">{filtersPanel}</div>
                <div className="sheet__foot">
                  {/* Filters apply live -- the URL is the state -- so «اعمال»
                      just closes the sheet and returns to the results, with
                      the count of active filters visible in the heading. */}
                  <button type="button" className="btn btn--primary" onClick={closeFilters}>
                    اعمال
                  </button>
                </div>
              </div>
            </Portal>
          ) : null}

          {sortOpen ? (
            <Portal>
              <button
                type="button"
                className="sheet-scrim"
                aria-label="بستن مرتب‌سازی"
                onClick={closeSort}
              />
              <div
                className="sheet"
                id="shop-sort-sheet"
                role="dialog"
                aria-modal="true"
                aria-label="مرتب‌سازی"
                ref={sortSheetRef}
              >
                <div className="sheet__head">
                  <h2>مرتب‌سازی</h2>
                  <button
                    type="button"
                    className="sheet__close"
                    aria-label="بستن"
                    onClick={closeSort}
                  >
                    <Icon name="close" size={16} />
                  </button>
                </div>
                <div className="sheet__body">
                  {SORT_OPTIONS.map((option) => (
                    <label key={option.value} className="sheet__option">
                      <input
                        type="radio"
                        name="shop-sorting"
                        value={option.value}
                        checked={(searchParams.get("ordering") || "newest") === option.value}
                        onChange={() => {
                          setParam("ordering", option.value);
                          closeSort();
                        }}
                      />
                      {option.label}
                    </label>
                  ))}
                </div>
                <div className="sheet__foot">
                  <button type="button" className="btn btn--outline" onClick={closeSort}>
                    بستن
                  </button>
                </div>
              </div>
            </Portal>
          ) : null}
        </>
      ) : null}

      <div className="shop__main">
        {/* Audit 19 item 1: on a phone the sticky toolbar lives INSIDE
            .shop__main -- whose box is the whole results list, so the bar can
            stick for the entire scroll (a grid item would only stick inside
            its own row). It carries filters, sorting and the result count,
            and is not rendered above 768px. */}
        {isMobile ? (
          <div className="shop__mobile-bar">
            <button
              type="button"
              className="shop__mobile-btn"
              aria-expanded={filtersOpen}
              aria-controls="shop-filters-sheet"
              onClick={() => setFiltersOpen(true)}
            >
              فیلترها
              {activeFilterCount > 0 ? (
                <span className="shop__mobile-btn__badge">{formatPrice(activeFilterCount)}</span>
              ) : null}
            </button>
            <button
              type="button"
              className="shop__mobile-btn"
              aria-expanded={sortOpen}
              aria-controls="shop-sort-sheet"
              onClick={() => setSortOpen(true)}
            >
              مرتب‌سازی
            </button>
            {products ? (
              <span className="shop__mobile-count">{formatPrice(products.count)} کالا</span>
            ) : null}
          </div>
        ) : null}

        <div className="shop__toolbar">
          {/* Part S2 item 7: result count, always derived from the server. */}
          {products ? <span className="shop__count">{formatPrice(products.count)} کالا</span> : null}
          <label>
            مرتب‌سازی:
            <select
              value={searchParams.get("ordering") || "newest"}
              onChange={(e) => setParam("ordering", e.target.value)}
            >
              {SORT_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </select>
          </label>
        </div>

        {searchParams.get("search") ? (
          <p className="shop__search-note">
            نتایج جستجو برای «{faDigits(searchParams.get("search"))}»
          </p>
        ) : null}

        {/* Part R2: visible active filters (e.g. arriving from a brand tile) */}
        {(() => {
          const brandSlug = fixedBrand ? null : searchParams.get("brand");
          const categorySlug = searchParams.get("category");
          const brand = (brandsState.data?.results || []).find((b) => b.slug === brandSlug);
          const category = (categoriesState.data?.results || []).find((c) => c.slug === categorySlug);
          const facets = facetsState.data?.results || [];
          const activeAttrs = attrKeys
            .map((key) => {
              const facet = facets.find((f) => f.slug === key.slice(5));
              return {
                key,
                // Fall back to the raw slug if the facet payload is not
                // loaded yet (label still stays human-deletable).
                name: facet ? facet.name : key.slice(5),
                values: selectedAttrValues(key.slice(5)).join("، "),
              };
            })
            .filter((entry) => entry.values);
          if (!brand && !category && activeAttrs.length === 0) return null;
          return (
            <div className="shop__chips">
              {brand ? (
                <span className="shop__chip">
                  برند: {faDigits(brand.name)}
                  <button type="button" aria-label="حذف فیلتر برند" onClick={() => setParam("brand", "")}>
                    <Icon name="close" size={14} />
                  </button>
                </span>
              ) : null}
              {category ? (
                <span className="shop__chip">
                  دسته: {faDigits(category.name)}
                  <button type="button" aria-label="حذف فیلتر دسته" onClick={() => setParam("category", "")}>
                    <Icon name="close" size={14} />
                  </button>
                </span>
              ) : null}
              {activeAttrs.map((entry) => (
                <span className="shop__chip" key={entry.key}>
                  {faDigits(entry.name)}: {faDigits(entry.values)}
                  <button type="button" aria-label={`حذف فیلتر ${entry.name}`} onClick={() => setParam(entry.key, "")}>
                    <Icon name="close" size={14} />
                  </button>
                </span>
              ))}
            </div>
          );
        })()}

        {/* Part S5 item 7: filtering is a transition, not a page reload. The
            spinner only covers the very first load; from then on the previous
            results stay on screen -- dimmed and aria-busy -- until the new
            page replaces them, so the layout never jumps. */}
        {/* Audit 19 item 1: the loading state is the SAME dense grid the
            results land in -- six card-shaped skeletons, so nothing shifts
            when the products (and then their images) arrive. */}
        {!products && productsState.isLoading ? (
          <div className="shop__skeleton" role="status" aria-busy="true" aria-label="در حال دریافت محصولات…">
            <span className="sr-only">در حال دریافت محصولات…</span>
            <div className="product-grid">
              {Array.from({ length: 6 }, (_, index) => (
                <ProductCardSkeleton key={index} />
              ))}
            </div>
          </div>
        ) : null}
        {productsState.error ? <ErrorState message={errorMessage(normalizeApiError(productsState.error))} onRetry={productsState.refetch} /> : null}

        {products ? (
          <div
            className={`shop__results${productsState.isLoading ? " shop__results--loading" : ""}`}
            aria-busy={productsState.isLoading || undefined}
          >
            {products.results.length === 0 ? (
              <EmptyState title="محصولی با این مشخصات پیدا نشد.">
                <p className="muted">فیلترها یا عبارت جستجو را تغییر دهید، یا همه فیلترها را حذف کنید.</p>
                <button type="button" className="btn btn--outline" onClick={clearAllFilters}>
                  حذف همه فیلترها
                </button>
              </EmptyState>
            ) : (
              <div className="product-grid">
                {products.results.map((product, index) => (
                  <div
                    className="product-grid__cell"
                    // A fresh page re-keys the cells so every card replays its
                    // fade+rise; the media boxes are aspect-ratio sized, so
                    // remounting cannot shift the layout.
                    key={`${resultsKey}-${product.id}`}
                    style={{ animationDelay: `${Math.min(index, MAX_STAGGER_STEPS) * 20}ms` }}
                  >
                    <ProductCard product={product} />
                  </div>
                ))}
              </div>
            )}
          </div>
        ) : null}

        {/* Phones: one «نمایش کالاهای بیشتر» button that walks the SAME
            ?page= URLs the numbered links use (so links stay shareable and
            the back button keeps working); every page up to N is fetched and
            rendered concatenated. Desktop keeps the numbered pagination. */}
        {isMobile && totalPages > currentPage ? (
          <button
            type="button"
            className="btn btn--outline shop__load-more"
            onClick={() => setParam("page", String(currentPage + 1))}
          >
            نمایش کالاهای بیشتر
          </button>
        ) : null}

        {!isMobile && totalPages > 1 ? (
          <nav className="pagination" aria-label="صفحه‌بندی">
            {currentPage > 1 ? <Link to={`?${new URLSearchParams({ ...Object.fromEntries(searchParams), page: currentPage - 1 })}`}>قبلی</Link> : <span aria-disabled="true">قبلی</span>}
            {Array.from({length: totalPages}, (_, index) => index + 1)
              .filter(page => page === 1 || page === totalPages || Math.abs(page - currentPage) <= 2)
              .map(page => <Link key={page} aria-current={page === currentPage ? "page" : undefined}
                to={`?${new URLSearchParams({ ...Object.fromEntries(searchParams), page })}`}>{faDigits(page)}</Link>)}
            <span>صفحه {faDigits(params.page || 1)} از {faDigits(totalPages)}</span>
            {currentPage < totalPages ? <Link to={`?${new URLSearchParams({ ...Object.fromEntries(searchParams), page: currentPage + 1 })}`}>بعدی</Link> : <span aria-disabled="true">بعدی</span>}
          </nav>
        ) : null}
      </div>
    </div>
  );
}

ShopPage.propTypes = { brand: brandShape };

export default ShopPage;
