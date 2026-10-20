/*
 * The header's height measurement must be the BORDER-BOX height
 * (content + padding + border). PR 20's live bug: the expanded phone
 * header "measured" 190px (its own stale lock) or 232px (scrollHeight,
 * missing padding) while the content needed 246px, so the search row
 * spilled out of the bar and the spacer was too short.
 */
import { describe, expect, it } from "vitest";

import { measureBorderBoxHeight } from "./headerMeasure";

describe("measureBorderBoxHeight", () => {
  it("returns the border-box height from getBoundingClientRect, padding included", () => {
    // Content 96 + padding 20 + border 2 = 118 border-box. scrollHeight
    // would say 96-116 (no border, padding only per spec quirks); the rect
    // is the full painted box the spacer has to reserve.
    const element = {
      getBoundingClientRect: () => ({ height: 118.4 }),
      offsetHeight: 118,
      scrollHeight: 96,
    };
    expect(measureBorderBoxHeight(element)).toBe(118);
  });

  it("prefers the rect over offsetHeight (a locked box re-reads its lock)", () => {
    const element = {
      getBoundingClientRect: () => ({ height: 246 }),
      offsetHeight: 190, // the stale lock from the old pinned height
      scrollHeight: 232,
    };
    expect(measureBorderBoxHeight(element)).toBe(246);
  });

  it("falls back to offsetHeight when the rect is 0 (jsdom, hidden tab)", () => {
    const element = {
      getBoundingClientRect: () => ({ height: 0 }),
      offsetHeight: 76,
      scrollHeight: 70,
    };
    expect(measureBorderBoxHeight(element)).toBe(76);
  });

  it("tolerates a missing element or missing layout APIs", () => {
    expect(measureBorderBoxHeight(null)).toBe(0);
    expect(measureBorderBoxHeight(undefined)).toBe(0);
    expect(measureBorderBoxHeight({})).toBe(0);
    expect(measureBorderBoxHeight({ offsetHeight: 56 })).toBe(56);
  });
});
