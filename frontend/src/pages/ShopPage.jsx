import { usePageMeta } from "../hooks/usePageMeta";
import { useEffect, useMemo } from "react";
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
  usePageMeta({
    title: filtered ? filtered.name : "فروشگاه",
    path: "/shop/",
    description:
      (selectedCategory && selectedCategory.description) ||
      (filtered
        ? `خرید آنلاین ${filtered.name} از کازین گالری؛ ارسال به سراسر ایران.`
        : "خرید آنلاین ظروف آشپزخانه، پخت‌وپز، بلور و کریستال و لوازم خانه با ارسال به سراسر ایران."),
    image: filtered
      ? shareImageUrl(selectedCategory ? selectedCategory.image : selectedBrand.tile_image || selectedBrand.logo)
      : undefined,
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

  const clearAllFilters = () => {
    const next = new URLSearchParams(searchParams);
    ["category", "brand", "min_price", "max_price", "in_stock", "page", ...attrKeys].forEach((k) => next.delete(k));
    setSearchParams(next);
  };

  // Attribute facet keys currently present in the URL (e.g. ["attr_rang"]).
  const attrKeys = [...searchParams.keys()].filter(
    (key) => key.startsWith("attr_") && searchParams.get(key)
  );

  return (
    <div className="shop">
      <aside className="shop__sidebar">
        <h2>فیلترها</h2>

        <div className="filter-group">
          <h3>دسته‌بندی</h3>
          <select
            value={searchParams.get("category") || ""}
            onChange={(e) => setParam("category", e.target.value)}
          >
            <option value="">همه دسته‌ها</option>
            {(categoriesState.data?.results || []).map((category) => (
              <option key={category.id} value={category.slug}>{category.name}</option>
            ))}
          </select>
        </div>

        <div className="filter-group">
          <h3>برند</h3>
          <select
            value={searchParams.get("brand") || ""}
            onChange={(e) => setParam("brand", e.target.value)}
          >
            <option value="">همه برندها</option>
            {(brandsState.data?.results || []).map((brand) => (
              <option key={brand.id} value={brand.slug}>{brand.name}</option>
            ))}
          </select>
        </div>

        {/* Part R5 item 8: dynamic attribute facets, one checkbox group
            per attribute that exists on active products (re-scoped to
            the selected category). */}
        {(facetsState.data?.results || []).map((attribute) => {
          const selected = selectedAttrValues(attribute.slug);
          return (
            <div className="filter-group" key={attribute.slug}>
              <h3>{attribute.name}</h3>
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
            </div>
          );
        })}

        <div className="filter-group">
          <h3>محدوده قیمت (تومان)</h3>
          <div className="filter-group__row">
            <input
              type="number"
              min="0"
              placeholder="از"
              defaultValue={searchParams.get("min_price") || ""}
              onBlur={(e) => setParam("min_price", e.target.value)}
            />
            <input
              type="number"
              min="0"
              placeholder="تا"
              defaultValue={searchParams.get("max_price") || ""}
              onBlur={(e) => setParam("max_price", e.target.value)}
            />
          </div>
        </div>

        <div className="filter-group">
          <label className="checkbox">
            <input
              type="checkbox"
              checked={searchParams.get("in_stock") === "true"}
              onChange={(e) => setParam("in_stock", e.target.checked ? "true" : "")}
            />
            فقط کالاهای موجود
          </label>
        </div>

        {(searchParams.get("category") || searchParams.get("brand") || searchParams.get("min_price") || searchParams.get("max_price") || searchParams.get("in_stock") || attrKeys.length > 0) ? (
          <button type="button" className="btn btn--outline btn--sm" onClick={clearAllFilters}>
            حذف همه فیلترها
          </button>
        ) : null}
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

        {productsState.isLoading ? <Spinner label="در حال دریافت محصولات…" /> : null}
        {productsState.error ? <ErrorState message={errorMessage(normalizeApiError(productsState.error))} onRetry={productsState.refetch} /> : null}

        {products && products.results.length === 0 ? (
          <EmptyState title="محصولی با این مشخصات پیدا نشد.">
            <p className="muted">فیلترها یا عبارت جستجو را تغییر دهید، یا همه فیلترها را حذف کنید.</p>
            <button type="button" className="btn btn--outline" onClick={clearAllFilters}>
              حذف همه فیلترها
            </button>
          </EmptyState>
        ) : null}

        {products?.results?.length ? (
          <div className="product-grid">
            {products.results.map((product) => (
              <ProductCard key={product.id} product={product} />
            ))}
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
