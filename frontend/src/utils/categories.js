import { normalizePersianText } from "./persianText";

/**
 * Root identity is API metadata or the top-level Persian name, NEVER a
 * preferred slug. Migration 0006 can produce kitchen-root(-N) when an
 * unrelated category already owns kitchen; published slugs may change too.
 */
export function isCatalogRoot(category) {
  if (!category || typeof category !== "object") return false;
  if (typeof category.is_root === "boolean") return category.is_root;
  return category.parent == null && !category.parent_slug
    && normalizePersianText(category.name) === "آشپزخانه";
}

/** Main groups are the root's children, with a safe legacy-tree fallback. */
export function mainGroups(roots) {
  const list = Array.isArray(roots) ? roots : [];
  const root = list.find(isCatalogRoot);
  return root ? root.children || [] : list;
}

/**
 * Pass the category object so root breadcrumbs map to /shop/ regardless
 * of its slug. A slug-only caller can supply the flat API list; otherwise
 * it remains a literal filter, not a guessed root identity.
 */
export function categoryUrl(category, flatList = []) {
  const slug = typeof category === "string" ? category : category?.slug;
  if (!slug) return "/shop/";
  const row = typeof category === "object"
    ? category
    : (Array.isArray(flatList) ? flatList : []).find((item) => item.slug === slug);
  if (isCatalogRoot(row)) return "/shop/";
  return `/shop/?category=${encodeURIComponent(slug)}`;
}

/**
 * Ancestor chain (top-most first, INCLUDING the given category
 * itself) for a category slug, resolved from the FLAT category
 * list (each row carries `parent_slug`). Returns null when the
 * slug is unknown. Guarded against cycles/pathological depth.
 */
export function categoryChain(slug, flatList) {
  const list = Array.isArray(flatList) ? flatList : [];
  const bySlug = new Map(list.map((category) => [category.slug, category]));
  const chain = [];
  let node = slug ? bySlug.get(slug) : null;
  let guard = 0;
  while (node && guard < 10) {
    chain.unshift(node);
    node = node.parent_slug ? bySlug.get(node.parent_slug) : null;
    guard += 1;
  }
  return slug && chain.length === 0 ? [{ slug, name: slug }] : chain;
}

/**
 * Stage 2: drop categories with no active products anywhere in
 * their subtree (the tree API annotates every node with
 * `product_count`). A node whose count is missing (mocked trees
 * in tests, older payloads) is assumed non-empty rather than
 * dropped -- emptiness must be PROVEN, never guessed.
 */
export function pruneEmptyCategories(categories) {
  return (Array.isArray(categories) ? categories : [])
    .map((category) => ({
      ...category,
      children: pruneEmptyCategories(category.children),
    }))
    .filter((category) => {
      if (typeof category.product_count !== "number") return true;
      return category.product_count > 0 || (category.children || []).length > 0;
    });
}

/**
 * The menu-ready catalog: main groups (children of the
 * «آشپزخانه» root), pruned of empty subtrees.
 */
export function catalogGroups(roots) {
  return pruneEmptyCategories(mainGroups(roots));
}
