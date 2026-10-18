/**
 * Stage 1 helpers for the single-root catalog tree.
 *
 * The backend has exactly ONE catalog root («آشپزخانه»), marked with
 * the API flag `is_catalog_root` (categories migration 0007).
 * Everything a shopper browses lives under it. Surfaces that
 * present "the main groups" (header mega menu, home category
 * tiles, shop filters) must show its CHILDREN -- never the root
 * itself, which would render as one useless tile.
 *
 * Root identity is the flag alone. Migration 0006 may publish the
 * root as kitchen-root(-N), and the owner may rename it (name or
 * slug) afterwards, so no helper may fall back to either field.
 */

/** The catalog-root row of a root list, by flag. */
export function catalogRoot(roots) {
  const list = Array.isArray(roots) ? roots : [];
  return list.find((category) => category.is_catalog_root === true) || null;
}

/** True when this category OBJECT is the flagged catalog root. */
export function isCatalogRoot(category) {
  return Boolean(category) && typeof category === "object" && category.is_catalog_root === true;
}

/** True when a category object (or a slug, resolved in `flatList`) is the root. */
export function isCatalogRootCategory(category, flatList) {
  if (!category) return false;
  if (typeof category === "object") return isCatalogRoot(category);
  const list = Array.isArray(flatList) ? flatList : [];
  return list.some((item) => item.slug === category && item.is_catalog_root === true);
}

/**
 * The main groups of the catalog: the children of the catalog
 * root. Falls back to the given roots when there is no flagged
 * root (unmigrated data / test fixtures).
 */
export function mainGroups(roots) {
  const list = Array.isArray(roots) ? roots : [];
  const root = catalogRoot(list);
  if (!root) return list;
  return root.children || [];
}

/**
 * Shop URL for a category. The catalog root has no products
 * of its own (it is a grouping node), so it maps to the shop
 * itself instead of a dead filter.
 *
 * Pass the category OBJECT so the root is recognised by its flag.
 * A slug-only caller can supply the flat API list; otherwise the
 * slug is treated as a literal filter, never as a guessed root.
 */
export function categoryUrl(category, flatList = []) {
  const slug = typeof category === "string" ? category : category?.slug;
  if (!slug) return "/shop/";
  if (isCatalogRootCategory(category, flatList)) return "/shop/";
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

/** The menu-ready catalog: main groups, pruned of empty subtrees. */
export function catalogGroups(roots) {
  return pruneEmptyCategories(mainGroups(roots));
}
