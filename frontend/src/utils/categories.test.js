/**
 * Stage 1: the single-root catalog helpers. The tree API now
 * returns one flagged root (with any slug) with the main groups
 * as its children -- these helpers decide what each storefront
 * surface shows. Root identity is `is_catalog_root`, never a name
 * or slug.
 */
import { describe, expect, it } from "vitest";

import {
  catalogRoot,
  categoryChain,
  categoryUrl,
  isCatalogRoot,
  isCatalogRootCategory,
  mainGroups,
} from "./categories";

const TREE = [
  {
    id: 1,
    name: "آشپزخانه",
    slug: "kitchen-root",
    is_catalog_root: true,
    children: [
      { id: 2, name: "ظروف پخت", slug: "cookware", is_catalog_root: false, children: [] },
      {
        id: 3,
        name: "قاشق، چنگال و کارد",
        slug: "cutlery",
        is_catalog_root: false,
        children: [{ id: 4, name: "قاشق", slug: "spoon", children: [] }],
      },
    ],
  },
];

const FLAT = [
  { id: 1, name: "آشپزخانه", slug: "kitchen-root", is_catalog_root: true, parent_slug: null },
  { id: 2, name: "ظروف پخت", slug: "cookware", is_catalog_root: false, parent_slug: "kitchen-root" },
  {
    id: 3,
    name: "قاشق، چنگال و کارد",
    slug: "cutlery",
    is_catalog_root: false,
    parent_slug: "kitchen-root",
  },
  { id: 4, name: "قاشق", slug: "spoon", is_catalog_root: false, parent_slug: "cutlery" },
];

describe("root identity", () => {
  it("uses only the API flag, regardless of the published slug", () => {
    expect(isCatalogRoot({ name: "آشپزخانه", slug: "kitchen-root-2", is_catalog_root: true })).toBe(true);
    expect(isCatalogRoot({ name: "گروه اصلی", slug: "catalog", is_catalog_root: true })).toBe(true);
    expect(isCatalogRoot({ name: "آشپزخانه", slug: "nested", is_catalog_root: false })).toBe(false);
  });

  it("never falls back to the Persian name or the kitchen slug", () => {
    expect(isCatalogRoot({ name: "آشپزخانه", slug: "kitchen-root", parent: null })).toBe(false);
    expect(isCatalogRoot({ name: "آشپزخانه", slug: "kitchen", parent: null })).toBe(false);
    expect(isCatalogRoot({ name: "دسته قدیمی", slug: "kitchen", parent: null })).toBe(false);
    expect(isCatalogRoot(null)).toBe(false);
    expect(isCatalogRoot("kitchen")).toBe(false);
  });

  it("never flattens a legacy kitchen category instead of the actual root", () => {
    const legacy = { name: "دسته قدیمی", slug: "kitchen", is_catalog_root: false, children: [] };
    const groups = mainGroups([{ ...TREE[0], children: [...TREE[0].children, legacy] }]);
    expect(groups.map((row) => row.slug)).toEqual(["cookware", "cutlery", "kitchen"]);
    expect(categoryUrl(legacy)).toBe("/shop/?category=kitchen");
    expect(categoryUrl("kitchen")).toBe("/shop/?category=kitchen");
    expect(categoryUrl("kitchen", FLAT)).toBe("/shop/?category=kitchen");
  });
});

describe("mainGroups", () => {
  it("returns the children of the flagged root, not the root", () => {
    const groups = mainGroups(TREE);
    expect(groups.map((c) => c.slug)).toEqual(["cookware", "cutlery"]);
    // The root itself never leaks into the main groups.
    expect(groups.find((c) => c.is_catalog_root)).toBeUndefined();
  });

  it("falls back to the raw roots when there is no flagged root", () => {
    // Unmigrated data / test fixtures without the root.
    const legacy = [{ id: 9, name: "Legacy", slug: "legacy", children: [] }];
    expect(mainGroups(legacy)).toEqual(legacy);
  });

  it("returns an empty list for an empty tree", () => {
    expect(mainGroups([])).toEqual([]);
    expect(mainGroups(undefined)).toEqual([]);
  });

  it("returns no groups when the flagged root is childless", () => {
    expect(
      mainGroups([{ id: 1, name: "آشپزخانه", slug: "kitchen", is_catalog_root: true, children: [] }])
    ).toEqual([]);
  });
});

describe("catalog root by flag (Task 3)", () => {
  // A renamed root: BOTH name and slug changed after migration 0007.
  const RENAMED_TREE = [
    {
      id: 1,
      name: "خانه و آشپزخانه",
      slug: "home",
      is_catalog_root: true,
      children: [
        { id: 2, name: "ظروف پخت", slug: "cookware", is_catalog_root: false, children: [] },
      ],
    },
  ];
  const RENAMED_FLAT = [
    { id: 1, name: "خانه و آشپزخانه", slug: "home", parent_slug: null, is_catalog_root: true },
    { id: 2, name: "ظروف پخت", slug: "cookware", parent_slug: "home", is_catalog_root: false },
  ];

  it("finds the renamed root by flag, not by name/slug", () => {
    expect(catalogRoot(RENAMED_TREE).slug).toBe("home");
    expect(mainGroups(RENAMED_TREE).map((c) => c.slug)).toEqual(["cookware"]);
  });

  it("maps the renamed root to the shop by flag", () => {
    expect(categoryUrl(RENAMED_TREE[0])).toBe("/shop/");
    expect(categoryUrl("home", RENAMED_FLAT)).toBe("/shop/");
    expect(isCatalogRootCategory(RENAMED_TREE[0])).toBe(true);
    expect(isCatalogRootCategory(RENAMED_TREE[0].children[0])).toBe(false);
    expect(isCatalogRootCategory("home", RENAMED_FLAT)).toBe(true);
    expect(isCatalogRootCategory("cookware", RENAMED_FLAT)).toBe(false);
  });

  it("does not treat a same-slug group as root when the flag says no", () => {
    const impostor = { id: 5, name: "آشپزی", slug: "kitchen", is_catalog_root: false };
    expect(isCatalogRootCategory(impostor)).toBe(false);
    expect(isCatalogRootCategory("kitchen", [impostor])).toBe(false);
  });
});

describe("categoryUrl", () => {
  it("maps the kitchen root to the shop itself, not a dead filter", () => {
    expect(categoryUrl(TREE[0])).toBe("/shop/");
    expect(categoryUrl("kitchen-root", FLAT)).toBe("/shop/");
  });

  it("treats a slug-only call without the flat list as a literal filter", () => {
    expect(categoryUrl("kitchen-root")).toBe("/shop/?category=kitchen-root");
  });

  it("maps a group to its shop filter", () => {
    expect(categoryUrl("cutlery")).toBe("/shop/?category=cutlery");
    expect(categoryUrl(FLAT[1])).toBe("/shop/?category=cookware");
  });

  it("falls back to the shop when there is no slug", () => {
    expect(categoryUrl(null)).toBe("/shop/");
    expect(categoryUrl("")).toBe("/shop/");
  });
});

describe("categoryChain", () => {
  it("walks parent_slug up to the kitchen root, top-most first", () => {
    const chain = categoryChain("spoon", FLAT);
    expect(chain.map((c) => c.slug)).toEqual(["kitchen-root", "cutlery", "spoon"]);
  });

  it("returns the category itself for a main group", () => {
    expect(categoryChain("cookware", FLAT).map((c) => c.slug)).toEqual([
      "kitchen-root",
      "cookware",
    ]);
  });

  it("degrades to the raw slug when the category is unknown", () => {
    expect(categoryChain("ghost", FLAT)).toEqual([{ slug: "ghost", name: "ghost" }]);
  });

  it("returns an empty chain for an empty slug", () => {
    expect(categoryChain(null, FLAT)).toEqual([]);
    expect(categoryChain("", FLAT)).toEqual([]);
  });

  it("never loops forever on a cyclic parent chain", () => {
    const cyclic = [
      { id: 1, name: "A", slug: "a", parent_slug: "b" },
      { id: 2, name: "B", slug: "b", parent_slug: "a" },
    ];
    const chain = categoryChain("a", cyclic);
    expect(chain.length).toBeLessThanOrEqual(10);
  });
});
