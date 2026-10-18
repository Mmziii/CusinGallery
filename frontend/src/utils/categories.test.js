/**
 * Stage 1: the single-root catalog helpers. The tree API now
 * returns one named/flagged root (with any slug) with
 * the main groups as its children -- these helpers decide
 * what each storefront surface shows.
 */
import { describe, expect, it } from "vitest";

import { categoryChain, categoryUrl, isCatalogRoot, mainGroups } from "./categories";

const TREE = [
  {
    id: 1,
    name: "آشپزخانه",
    slug: "kitchen-root", is_root: true,
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
  { id: 1, name: "آشپزخانه", slug: "kitchen-root", is_root: true, parent_slug: null },
  { id: 2, name: "ظروف پخت", slug: "cookware", parent_slug: "kitchen-root" },
  {
    id: 3,
    name: "قاشق، چنگال و کارد",
    slug: "cutlery",
    parent_slug: "kitchen-root",
  },
  { id: 4, name: "قاشق", slug: "spoon", parent_slug: "cutlery" },
];

describe("root identity", () => {
  it("uses the API flag or the single top-level Persian name, regardless of slug", () => {
    expect(isCatalogRoot({ name: "آشپزخانه", slug: "kitchen-root-2", parent: null })).toBe(true);
    expect(isCatalogRoot({ name: "گروه اصلی", slug: "catalog", is_root: true })).toBe(true);
    expect(isCatalogRoot({ name: "آشپزخانه", slug: "nested", parent: 1 })).toBe(false);
    expect(isCatalogRoot({ name: "آشپزخانه", slug: "nested", is_root: false })).toBe(false);
    expect(isCatalogRoot({ name: "دسته قدیمی", slug: "kitchen", parent: null })).toBe(false);
  });

  it("never flattens a legacy kitchen category instead of the actual root", () => {
    const legacy = { name: "دسته قدیمی", slug: "kitchen", is_root: false, children: [] };
    const groups = mainGroups([{ ...TREE[0], children: [...TREE[0].children, legacy] }]);
    expect(groups.map((row) => row.slug)).toEqual(["cookware", "cutlery", "kitchen"]);
    expect(categoryUrl(legacy)).toBe("/shop/?category=kitchen");
    expect(categoryUrl("kitchen")).toBe("/shop/?category=kitchen");
  });
});

describe("mainGroups", () => {
  it("returns the children of the kitchen root, not the root", () => {
    const groups = mainGroups(TREE);
    expect(groups.map((c) => c.slug)).toEqual(["cookware", "cutlery"]);
    // The root itself never leaks into the main groups.
    expect(groups.find((c) => c.is_root)).toBeUndefined();
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

describe("categoryUrl", () => {
  it("maps the kitchen root to the shop itself, not a dead filter", () => {
    expect(categoryUrl(TREE[0])).toBe("/shop/");
    expect(categoryUrl("kitchen-root", FLAT)).toBe("/shop/");
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
      "kitchen-root",
      "cutlery",
      "spoon",
    ]);
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
