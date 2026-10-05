/**
 * Part R5 item 10: the browser-local recently-viewed store.
 * Pure localStorage behavior -- no server involved anywhere.
 */
import { beforeEach, describe, expect, it } from "vitest";

import { RECENT_KEY, RECENT_LIMIT, getRecentlyViewed, recordView } from "./recentlyViewed";

beforeEach(() => {
  localStorage.clear();
});

describe("recentlyViewed store", () => {
  it("starts empty", () => {
    expect(getRecentlyViewed()).toEqual([]);
  });

  it("records views most-recent-first and deduplicates", () => {
    recordView(1);
    recordView(2);
    recordView(3);
    expect(getRecentlyViewed()).toEqual([3, 2, 1]);

    // Re-viewing 1 promotes it to the front instead of duplicating.
    recordView(1);
    expect(getRecentlyViewed()).toEqual([1, 3, 2]);
  });

  it("caps the list at 12 entries", () => {
    for (let id = 1; id <= 20; id += 1) recordView(id);
    const list = getRecentlyViewed();
    expect(list.length).toBe(RECENT_LIMIT);
    expect(list.length).toBe(12);
    expect(list[0]).toBe(20); // newest first
    expect(list[list.length - 1]).toBe(9); // oldest nine entries dropped
  });

  it("ignores non-positive or non-integer ids", () => {
    recordView(0);
    recordView(-3);
    recordView(1.5);
    recordView(null);
    recordView(undefined);
    expect(getRecentlyViewed()).toEqual([]);
  });

  it("drops corrupt storage content instead of throwing", () => {
    localStorage.setItem(RECENT_KEY, "{not-json");
    expect(getRecentlyViewed()).toEqual([]);
    recordView(7); // still usable afterwards
    expect(getRecentlyViewed()).toEqual([7]);
  });

  it("drops non-integer junk entries from storage", () => {
    localStorage.setItem(RECENT_KEY, JSON.stringify([5, "x", -1, 3.5, 9]));
    expect(getRecentlyViewed()).toEqual([5, 9]);
  });
});
