import { usePageMeta } from "../hooks/usePageMeta";
import { useMemo } from "react";
import { useSearchParams } from "react-router-dom";

import Icon from "../components/Icon";
import ProductCard from "../components/ProductCard";
import { EmptyState, ErrorState, Spinner } from "../components/ui";
import { useAsync } from "../hooks/useAsync";
import { listBrands, listCategories, listProducts } from "../services/catalogApi";
import { errorMessage } from "../components/ui";
import { normalizeApiError } from "../utils/apiError";

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
  usePageMeta({
    title: "فروشگاه",
    path: "/shop/",
    description: "خرید آنلاین ظروف آشپزخانه، پخت‌وپز، بلور و کریستال و لوازم خانه با ارسال به سراسر ایران.",
  });
  const [searchParams, setSearchParams] = useSearchParams();

  const params = useMemo(() => {
    const p = {};
    for (const key of ["search", "category", "brand", "min_price", "max_price", "in_stock", "ordering", "page"]) {
      const value = searchParams.get(key);
      if (value) p[key] = value;
    }
    return p;
  }, [searchParams]);

  const productsState = useAsync(() => listProducts(params), [searchParams.toString()]);
  const categoriesState = useAsync(() => listCategories(), []);
  const brandsState = useAsync(() => listBrands(), []);

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

  const products = productsState.data;
  const totalPages = products ? Math.ceil(products.count / 20) : 0;

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

        {(searchParams.get("category") || searchParams.get("brand") || searchParams.get("min_price") || searchParams.get("max_price") || searchParams.get("in_stock")) ? (
          <button type="button" className="btn btn--outline btn--sm" onClick={() => {
            const next = new URLSearchParams(searchParams);
            ["category", "brand", "min_price", "max_price", "in_stock", "page"].forEach((k) => next.delete(k));
            setSearchParams(next);
          }}>
            حذف فیلترها
          </button>
        ) : null}
      </aside>

      <div className="shop__main">
        <div className="shop__toolbar">
          <h1>فروشگاه</h1>
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
          if (!brand && !category) return null;
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
            </div>
          );
        })()}

        {productsState.isLoading ? <Spinner label="در حال دریافت محصولات…" /> : null}
        {productsState.error ? <ErrorState message={errorMessage(normalizeApiError(productsState.error))} onRetry={productsState.refetch} /> : null}

        {products && products.results.length === 0 ? (
          <EmptyState title="محصولی با این مشخصات پیدا نشد." />
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
