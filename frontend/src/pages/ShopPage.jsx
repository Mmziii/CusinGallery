import PropTypes from "prop-types";
import { usePageMeta } from "../hooks/usePageMeta";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigationType, useSearchParams } from "react-router-dom";

import Breadcrumbs from "../components/Breadcrumbs";
import Icon from "../components/Icon";
import ProductCard from "../components/ProductCard";
import { EmptyState, ErrorState, Spinner } from "../components/ui";
import { useAsync } from "../hooks/useAsync";
import { listBrands, listCategories, listFacets, listProducts } from "../services/catalogApi";
import { errorMessage } from "../components/ui";
import { normalizeApiError } from "../utils/apiError";
import { formatPrice } from "../utils/formatPrice";
import { shareImageUrl } from "../utils/shareImage";

/** Part S5 item 7: price inputs wait ~300ms after the last keystroke. */
const PRICE_DEBOUNCE_MS = 300;

/** Small debounce hook for the price range inputs. */
function useDebouncedCallback(callback, delay) {
  const timer = useRef(null);
  const latest = useRef(callback);
  latest.current = callback;
  useEffect(() => () => clearTimeout(timer.current), []);
  return useCallback(
    (...args) => {
      clearTimeout(timer.current);
      timer.current = setTimeout(() => latest.current(...args), delay);
    },
    [delay]
  );
}

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
function ShopPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  // Part S5 item 7: on small screens the whole filter column collapses
  // into a drawer; the open/close transition is a grid-template-rows
  // 0fr -> 1fr animation (same technique as the filter groups).
  const [filtersOpen, setFiltersOpen] = useState(false);

  const params = useMemo(() => {
    const p = {};
    for (const key of ["search", "category", "brand", "min_price", "max_price", "in_stock", "ordering", "page"]) {
      const value = searchParams.get(key);
      if (value) p[key] = value;
    }
    // Part R5 item 8: attribute facet filters live in attr_<attribute-slug>
    // params (comma-joined values) and are forwarded verbatim to the API.
    for (const key of searchParams.keys()) {
      const value = searchParams.get(key);
      if (key.startsWith("attr_") && value) p[key] = value;
    }
    return p;
  }, [searchParams]);

  const productsState = useAsync(() => listProducts(params), [searchParams.toString()]);
  const categoriesState = useAsync(() => listCategories(), []);
  const brandsState = useAsync(() => listBrands(), []);
  // Facets re-scope whenever the selected category changes; the facet
  // counts then only cover that category's products.
  const facetsState = useAsync(
    () => listFacets(params.category ? { category: params.category } : {}),
    [params.category || ""]
  );

  // Part S4 item 2: a category or brand page shares ITS OWN image (the
  // category image, or the brand tile with the brand logo as fallback) as
  // an absolute URL, and falls back to the shared brand placeholder when
  // that item has no image at all. An unfiltered /shop/ keeps the
  // site-wide og:image from index.html.
  const categories = categoriesState.data?.results || [];
  const brands = brandsState.data?.results || [];
  const selectedCategory = categories.find((c) => c.slug === params.category) || null;
  const selectedBrand = brands.find((b) => b.slug === params.brand) || null;
  const filtered = selectedCategory || selectedBrand;
  // Built by the shared helper (never by string concatenation): the
  // category image, the brand tile (or its logo), the placeholder.
  const listingShareImage = filtered
    ? shareImageUrl(selectedCategory ? selectedCategory.image : selectedBrand.tile_image || selectedBrand.logo)
    : undefined;
  usePageMeta({
    title: filtered ? filtered.name : "فروشگاه",
    path: "/shop/",
    description:
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
  const totalPages = products ? Math.ceil(products.count / 20) : 0;

  // Part S2 item 7: preserve scroll position when the browser navigates
  // BACK to this listing (filters already survive via the URL). The
  // position is stored per filter-set, so forward navigation starts fresh.
  const navigationType = useNavigationType();
  useEffect(() => {
    const key = `cusin.shop.scroll.${searchParams.toString()}`;
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
  }, [searchParams, navigationType]);

  // Part S5 item 7: a new result set re-triggers the staggered entrance
  // (the key remounts the cards -- their boxes are aspect-ratio sized, so
  // remounting cannot shift the layout).
  const [resultsKey, setResultsKey] = useState(0);
  useEffect(() => {
    if (productsState.data) setResultsKey((value) => value + 1);
  }, [productsState.data]);

  // Part S5 item 7: the price inputs keep their own text state and push
  // the value into the URL ~300ms after the last keystroke (and at once on
  // blur), so typing never triggers a request per character.
  const [priceText, setPriceText] = useState({
    min_price: searchParams.get("min_price") || "",
    max_price: searchParams.get("max_price") || "",
  });
  const debouncedSetParam = useDebouncedCallback((key, value) => setParam(key, value), PRICE_DEBOUNCE_MS);
  const applyPrice = (key, value) => {
    setPriceText((current) => ({ ...current, [key]: value }));
    debouncedSetParam(key, value);
  };

  const clearAllFilters = () => {
    const next = new URLSearchParams(searchParams);
    ["category", "brand", "min_price", "max_price", "in_stock", "page", ...attrKeys].forEach((k) => next.delete(k));
    setPriceText({ min_price: "", max_price: "" });
    setSearchParams(next);
  };

  // Attribute facet keys currently present in the URL (e.g. ["attr_rang"]).
  const attrKeys = [...searchParams.keys()].filter(
    (key) => key.startsWith("attr_") && searchParams.get(key)
  );

  return (
    <div className="shop">
      <aside className="shop__sidebar">
        {/* Part S5 item 7: on small screens the filter column folds into a
            drawer; the open/close motion is the same grid-template-rows
            0fr -> 1fr transition the groups use. The panel stays in the
            DOM, so nothing is lost when it is closed. */}
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
          <div className="shop__filters-inner">
            <h2>فیلترها</h2>

            <FilterGroup title="دسته‌بندی">
              <select
                value={searchParams.get("category") || ""}
                onChange={(e) => setParam("category", e.target.value)}
              >
                <option value="">همه دسته‌ها</option>
                {(categoriesState.data?.results || []).map((category) => (
                  <option key={category.id} value={category.slug}>{category.name}</option>
                ))}
              </select>
            </FilterGroup>

            <FilterGroup title="برند">
              <select
                value={searchParams.get("brand") || ""}
                onChange={(e) => setParam("brand", e.target.value)}
              >
                <option value="">همه برندها</option>
                {(brandsState.data?.results || []).map((brand) => (
                  <option key={brand.id} value={brand.slug}>{brand.name}</option>
                ))}
              </select>
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
                      {entry.value} <span className="filter-group__count">({entry.count})</span>
                    </label>
                  ))}
                </FilterGroup>
              );
            })}

            <FilterGroup title="محدوده قیمت (تومان)">
              <div className="filter-group__row">
                <input
                  type="number"
                  min="0"
                  placeholder="از"
                  aria-label="کمترین قیمت"
                  value={priceText.min_price}
                  onChange={(e) => applyPrice("min_price", e.target.value)}
                  onBlur={(e) => setParam("min_price", e.target.value)}
                />
                <input
                  type="number"
                  min="0"
                  placeholder="تا"
                  aria-label="بیشترین قیمت"
                  value={priceText.max_price}
                  onChange={(e) => applyPrice("max_price", e.target.value)}
                  onBlur={(e) => setParam("max_price", e.target.value)}
                />
              </div>
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

            {(searchParams.get("category") || searchParams.get("brand") || searchParams.get("min_price") || searchParams.get("max_price") || searchParams.get("in_stock") || attrKeys.length > 0) ? (
              <button type="button" className="btn btn--outline btn--sm" onClick={clearAllFilters}>
                حذف همه فیلترها
              </button>
            ) : null}
          </div>
        </div>
      </aside>

      <div className="shop__main">
        {/* Part S2 item 7: breadcrumbs (category name once loaded) */}
        <Breadcrumbs
          items={[
            { label: "خانه", to: "/" },
            { label: "فروشگاه", to: "/shop/" },
            ...(searchParams.get("category")
              ? [
                  {
                    label:
                      (categoriesState.data?.results || []).find(
                        (c) => c.slug === searchParams.get("category")
                      )?.name || searchParams.get("category"),
                  },
                ]
              : []),
          ]}
        />
        <div className="shop__toolbar">
          <h1>فروشگاه</h1>
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
            نتایج جستجو برای «{searchParams.get("search")}»
          </p>
        ) : null}

        {/* Part R2: visible active filters (e.g. arriving from a brand tile) */}
        {(() => {
          const brandSlug = searchParams.get("brand");
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
                  برند: {brand.name}
                  <button type="button" aria-label="حذف فیلتر برند" onClick={() => setParam("brand", "")}>
                    <Icon name="close" size={14} />
                  </button>
                </span>
              ) : null}
              {category ? (
                <span className="shop__chip">
                  دسته: {category.name}
                  <button type="button" aria-label="حذف فیلتر دسته" onClick={() => setParam("category", "")}>
                    <Icon name="close" size={14} />
                  </button>
                </span>
              ) : null}
              {activeAttrs.map((entry) => (
                <span className="shop__chip" key={entry.key}>
                  {entry.name}: {entry.values}
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
        {!products && productsState.isLoading ? <Spinner label="در حال دریافت محصولات…" /> : null}
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

        {totalPages > 1 ? (
          <nav className="pagination" aria-label="صفحه‌بندی">
            <button
              type="button"
              disabled={!products.previous}
              onClick={() => setParam("page", Number(params.page || 1) - 1)}
            >
              قبلی
            </button>
            <span>صفحه {params.page || 1} از {totalPages}</span>
            <button
              type="button"
              disabled={!products.next}
              onClick={() => setParam("page", Number(params.page || 1) + 1)}
            >
              بعدی
            </button>
          </nav>
        ) : null}
      </div>
    </div>
  );
}

export default ShopPage;
