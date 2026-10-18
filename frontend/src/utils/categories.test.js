/**
 * Stage 1: the single-root catalog helpers. The tree API now
 * returns exactly one root («آشپزخانه», slug kitchen) with
 * the main groups as its children -- these helpers decide
 * what each storefront surface shows.
 */
import { describe, expect, it } from "vitest";

import {
  catalogRoot,
  categoryChain,
  categoryUrl,
  categoryUrlFor,
  isCatalogRootCategory,
  KITCHEN_ROOT_SLUG,
  mainGroups,
} from "./categories";

const TREE = [
  {
    id: 1,
    name: "آشپزخانه",
    slug: "kitchen",
    children: [
      { id: 2, name: "ظروف پخت", slug: "cookware", children: [] },
      {
        id: 3,
        name: "قاشق، چنگال و کارد",
        slug: "cutlery",
        children: [{ id: 4, name: "قاشق", slug: "spoon", children: [] }],
      },
    ],
  },
];

const FLAT = [
  { id: 1, name: "آشپزخانه", slug: "kitchen", parent_slug: null },
  { id: 2, name: "ظروف پخت", slug: "cookware", parent_slug: "kitchen" },
  {
    id: 3,
    name: "قاشق، چنگال و کارد",
    slug: "cutlery",
    parent_slug: "kitchen",
  },
  { id: 4, name: "قاشق", slug: "spoon", parent_slug: "cutlery" },
];

describe("mainGroups", () => {
  it("returns the children of the kitchen root, not the root", () => {
    const groups = mainGroups(TREE);
    expect(groups.map((c) => c.slug)).toEqual(["cookware", "cutlery"]);
    // The root itself never leaks into the main groups.
    expect(groups.find((c) => c.slug === KITCHEN_ROOT_SLUG)).toBeUndefined();
  });

  it("falls back to the raw roots when there is no kitchen root", () => {
    // Unmigrated data / test fixtures without the root.
    const legacy = [{ id: 9, name: "Legacy", slug: "legacy", children: [] }];
    expect(mainGroups(legacy)).toEqual(legacy);
  });

  it("returns an empty list for an empty tree", () => {
    expect(mainGroups([])).toEqual([]);
    expect(mainGroups(undefined)).toEqual([]);
  });

  it("returns no groups when the kitchen root is childless", () => {
    expect(mainGroups([{ id: 1, name: "آشپزخانه", slug: "kitchen", children: [] }])).toEqual(
      []
    );
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
    expect(categoryUrlFor(RENAMED_TREE[0])).toBe("/shop/");
    expect(categoryUrl("home", RENAMED_FLAT)).toBe("/shop/");
    expect(isCatalogRootCategory(RENAMED_TREE[0])).toBe(true);
    expect(isCatalogRootCategory(RENAMED_TREE[0].children[0])).toBe(false);
  });

  it("does not treat a same-slug group as root when the flag says no", () => {
    const impostor = { id: 5, name: "آشپزی", slug: "kitchen", is_catalog_root: false };
    expect(isCatalogRootCategory(impostor)).toBe(false);
  });
});

describe("categoryUrl", () => {
  it("maps the kitchen root to the shop itself, not a dead filter", () => {
    expect(categoryUrl("kitchen")).toBe("/shop/");
  });

  it("maps a group to its shop filter", () => {
    expect(categoryUrl("cutlery")).toBe("/shop/?category=cutlery");
  });

  it("falls back to the shop when there is no slug", () => {
    expect(categoryUrl(null)).toBe("/shop/");
    expect(categoryUrl("")).toBe("/shop/");
  });
});

describe("categoryChain", () => {
  it("walks parent_slug up to the kitchen root, top-most first", () => {
    const chain = categoryChain("spoon", FLAT);
    expect(chain.map((c) => c.slug)).toEqual([
      "kitchen",
      "cutlery",
      "spoon",
    ]);
  });

  it("returns the category itself for a main group", () => {
    expect(categoryChain("cookware", FLAT).map((c) => c.slug)).toEqual([
      "kitchen",
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
