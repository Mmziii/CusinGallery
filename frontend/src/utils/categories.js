/**
 * Stage 1 helpers for the single-root catalog tree.
 *
 * The backend now has exactly ONE root category: «آشپزخانه»
 * (slug `kitchen`, see the categories 0006 data migration).
 * Everything a shopper browses lives under it. Surfaces that
 * present "the main groups" (header mega menu, home category
 * tiles, shop filters) must show its CHILDREN -- never the root
 * itself, which would render as one useless «آشپزخانه» tile.
 *
 * All helpers degrade gracefully when the tree has no kitchen
 * root (older API data, mocked trees in tests): they fall back
 * to the raw roots so nothing breaks before/after a deploy.
 */

export const KITCHEN_ROOT_SLUG = "kitchen";

/**
 * The main groups of the catalog: the children of the
 * «آشپزخانه» root. Falls back to the given roots when there
 * is no kitchen root (unmigrated data / test fixtures).
 */
export function mainGroups(roots) {
  const list = Array.isArray(roots) ? roots : [];
  const kitchen = list.find((category) => category.slug === KITCHEN_ROOT_SLUG);
  if (!kitchen) return list;
  return kitchen.children || [];
}

/**
 * Shop URL for a category slug. The kitchen root has no
 * products of its own (it is a grouping node), so it maps to
 * the shop itself instead of a dead `?category=kitchen` filter.
 */
export function categoryUrl(slug) {
  if (!slug) return "/shop/";
  if (slug === KITCHEN_ROOT_SLUG) return "/shop/";
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
