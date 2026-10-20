import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import apiClient from "../services/apiClient";
import Home from "./Home";

/** The real stylesheet: jsdom cannot animate, so the motion contract is a
 *  source assertion (same pattern as the mobile audit tests). */
const CSS = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), "..", "styles", "storefront.css"),
  "utf8"
).replace(/\s+/g, " ");

const originalAdapter = apiClient.defaults.adapter;
const SERVER_NOW = "2026-10-18T12:00:00.000Z";

const deal = (id, name, slug, overrides = {}) => ({
  id,
  sale_price: 50000,
  starts_at: "2026-10-18T10:00:00.000Z",
  ends_at: "2026-10-18T18:00:00.000Z",
  product: {
    id: 100 + id,
    name,
    slug,
    primary_image: { image: `/img${id}.jpg`, alt_text: name },
    price_info: { price: 100000, compare_at_price: null },
  },
  ...overrides,
});

const DAILY_DEAL = {
  count: 1,
  next: null,
  previous: null,
  server_now: SERVER_NOW,
  results: [
    {
      id: 17,
      sale_price: 85000,
      starts_at: "2026-10-18T11:00:00.000Z",
      ends_at: "2026-10-18T15:02:09.000Z",
      product: {
        id: 42,
        name: "پارچ مدل 123",
        slug: "pitcher-model-123",
        primary_image: null,
        price_info: {
          price: 100000,
          compare_at_price: null,
          discount_percentage: 4,
          is_on_sale: false,
          discount_amount: 0,
        },
      },
    },
  ],
};

const MULTI_DEALS = {
  count: 2,
  server_now: SERVER_NOW,
  results: [
    deal(1, "کالای اول", "item-1", { sale_price: 50000 }),
    deal(2, "کالای دوم", "item-2", { sale_price: 70000 }),
  ],
};

const THREE_DEALS = {
  count: 3,
  server_now: SERVER_NOW,
  results: [deal(1, "کالای اول", "item-1"), deal(2, "کالای دوم", "item-2"), deal(3, "کالای سوم", "item-3")],
};

const SIX_DEALS = {
  count: 6,
  server_now: SERVER_NOW,
  results: [
    deal(1, "کالای اول", "item-1"),
    deal(2, "کالای دوم", "item-2"),
    deal(3, "کالای سوم", "item-3"),
    deal(4, "کالای چهارم", "item-4"),
    deal(5, "کالای پنجم", "item-5"),
    deal(6, "کالای ششم", "item-6"),
  ],
};

const originalMatchMedia = window.matchMedia;

function serveDeals(payload) {
  apiClient.defaults.adapter = async (config) => {
    if ((config.url || "").includes("/banners/daily-deals/")) {
      return { data: payload, status: 200, statusText: "OK", headers: {}, config };
    }
    return originalAdapter(config);
  };
}

/** Phone-sized viewport (the deals band is a different layout there). */
function setViewport(mobile) {
  window.matchMedia = (query) => ({
    matches: mobile && query.includes("max-width: 767px"),
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  });
}

/** The live URL, so "a side card does not navigate" can be asserted. */
function LocationProbe() {
  const location = useLocation();
  return (
    <output data-testid="location" hidden>
      {location.pathname}
    </output>
  );
}

function renderHome() {
  return render(
    <MemoryRouter>
      <Home />
      <LocationProbe />
    </MemoryRouter>
  );
}

/** Desktop coverflow cards, in DOM order. */
const cards = (container) => [...container.querySelectorAll(".deals-cf__card")];
const cardAt = (container, offset) => container.querySelector(`.deals-cf__card[data-offset="${offset}"]`);
const centreCard = (container) => container.querySelector(".deals-cf__card.is-centre");
const centreName = (container) => centreCard(container)?.querySelector(".deal-card__name")?.textContent;

beforeEach(() => {
  serveDeals(DAILY_DEAL);
});

afterEach(() => {
  cleanup();
  apiClient.defaults.adapter = originalAdapter;
  window.matchMedia = originalMatchMedia;
  vi.useRealTimers();
});

describe("homepage daily deal", () => {
  it("renders the actual deal discount, old price, Persian name and labeled Persian countdown", async () => {
    const { container } = renderHome();

    const dealName = await screen.findByText("پارچ مدل ۱۲۳");
    expect(dealName.className).toContain("deal-card__name");
    expect(dealName.closest("a").getAttribute("href")).toBe("/products/pitcher-model-123/");
    expect(screen.getByText("۱۵٪ تخفیف")).toBeTruthy();
    expect(container.querySelector(".deal-card__regular").textContent).toBe("۱۰۰٬۰۰۰ تومان");
    expect(container.querySelector(".deal-card__sale").textContent).toBe("۸۵٬۰۰۰ تومان");

    const timer = await screen.findByRole("timer", { name: "زمان باقی‌مانده" });
    expect(within(timer).getByText("۰۳")).toBeTruthy();
    expect(within(timer).getByText("۰۲")).toBeTruthy();
    expect(within(timer).getByText("۰۹")).toBeTruthy();
    expect(timer.textContent).toContain("ساعت");
    expect(timer.textContent).toContain("دقیقه");
    expect(timer.textContent).toContain("ثانیه");
  });

  it("reads the countdown like a clock: hours, minutes, seconds in DOM order, laid out LTR", async () => {
    // PR 20: the segments run hours (left) -> minutes -> seconds (right)
    // with ":" separators and the Persian label under its own number;
    // `.countdown` carries direction:ltr so the flex row paints in that
    // order inside the RTL page. Digits stay Persian, the aria-label too.
    renderHome();
    const timer = await screen.findByRole("timer", { name: "زمان باقی‌مانده" });
    const values = [...timer.querySelectorAll(".countdown__value")].map((n) => n.textContent);
    const labels = [...timer.querySelectorAll(".countdown__label")].map((n) => n.textContent);
    // DAILY_DEAL: server_now 12:00:00, ends 15:02:09 -> 3h 2m 9s.
    expect(values).toEqual(["۰۳", "۰۲", "۰۹"]);
    expect(labels).toEqual(["ساعت", "دقیقه", "ثانیه"]);
    expect(timer.querySelectorAll(".countdown__sep")).toHaveLength(2);
    expect(CSS).toContain(".countdown { direction: ltr;");
  });

  it("does not render deals section when all deals are expired", async () => {
    serveDeals({
      count: 1,
      server_now: SERVER_NOW,
      results: [
        deal(99, "کالای منقضی", "expired-item", {
          starts_at: "2026-10-18T08:00:00.000Z",
          ends_at: "2026-10-18T10:00:00.000Z", // before server_now (12:00)
        }),
      ],
    });

    const { container } = renderHome();

    await new Promise((r) => setTimeout(r, 50));
    expect(screen.queryByText("کالای منقضی")).toBeNull();
    expect(container.querySelector(".deals-section")).toBeNull();
  });

  it("renders struck compare_at_price and correct percentage when price_info.price equals sale_price", async () => {
    serveDeals({
      count: 1,
      next: null,
      previous: null,
      server_now: SERVER_NOW,
      results: [
        {
          id: 55,
          sale_price: 199000,
          starts_at: "2026-10-18T10:00:00.000Z",
          ends_at: "2026-10-18T20:00:00.000Z",
          product: {
            id: 88,
            name: "سرویس قاشق و چنگال",
            slug: "cutlery-set",
            primary_image: null,
            price_info: { price: 199000, compare_at_price: 240000 },
          },
        },
      ],
    });

    const { container } = renderHome();

    const dealName = await screen.findByText("سرویس قاشق و چنگال");
    expect(dealName).toBeTruthy();

    expect(screen.getByText("۱۷٪ تخفیف")).toBeTruthy();
    const regularPriceEl = container.querySelector(".deal-card__regular");
    expect(regularPriceEl).toBeTruthy();
    expect(regularPriceEl.textContent).toContain("۲۴۰٬۰۰۰");
    expect(regularPriceEl.tagName).toBe("S");

    const salePriceEl = container.querySelector(".deal-card__sale");
    expect(salePriceEl).toBeTruthy();
    expect(salePriceEl.textContent).toContain("۱۹۹٬۰۰۰");
  });
});

describe("desktop coverflow layout", () => {
  it("places the centre card, ±1 and ±2 on their sides and hides the rest", async () => {
    serveDeals(SIX_DEALS);
    const { container } = renderHome();
    await screen.findByText("کالای اول");

    const centre = centreCard(container);
    expect(centre.getAttribute("data-offset")).toBe("0");
    expect(centre.className).toContain("is-centre");
    expect(centre.getAttribute("data-role")).toBe("centre");
    expect(centre.querySelector(".deal-card__name").textContent).toBe("کالای اول");
    // The centre card links to the product.
    expect(centre.querySelector("a").getAttribute("href")).toBe("/products/item-1/");
    expect(centre.querySelector("a").getAttribute("role")).toBeNull();

    // +1 = the next deal, drawn on the LEFT in RTL; -1 = previous, RIGHT.
    const nextOne = cardAt(container, "1");
    expect(nextOne.className).toContain("is-side");
    expect(nextOne.className).toContain("is-next");
    expect(nextOne.querySelector(".deal-card__name").textContent).toBe("کالای دوم");
    // Side cards only bring themselves to the centre.
    expect(nextOne.querySelector("a").getAttribute("role")).toBe("button");

    const prevOne = cardAt(container, "-1");
    expect(prevOne.className).toContain("is-prev");
    // With six deals, -1 wraps to the last one.
    expect(prevOne.querySelector(".deal-card__name").textContent).toBe("کالای ششم");

    // RTL geometry: the next card is offset to the LEFT (negative dx), the
    // previous one to the RIGHT (positive dx); the centre is at 0.
    expect(Number(centre.style.getPropertyValue("--cf-dx"))).toBe(0);
    expect(Number(nextOne.style.getPropertyValue("--cf-dx"))).toBeLessThan(0);
    expect(Number(prevOne.style.getPropertyValue("--cf-dx"))).toBeGreaterThan(0);
    // Scale/opacity fall off with the distance from the centre.
    expect(centre.style.getPropertyValue("--cf-scale")).toBe("1");
    expect(centre.style.getPropertyValue("--cf-opacity")).toBe("1");
    expect(Number(nextOne.style.getPropertyValue("--cf-scale"))).toBeCloseTo(0.8);
    expect(Number(nextOne.style.getPropertyValue("--cf-opacity"))).toBeCloseTo(0.45);
    expect(Number(cardAt(container, "2").style.getPropertyValue("--cf-scale"))).toBeLessThan(0.8);
    expect(Number(cardAt(container, "2").style.getPropertyValue("--cf-opacity"))).toBeLessThan(0.45);
    // ...and the centre card is on top.
    expect(Number(centre.style.zIndex)).toBeGreaterThan(Number(nextOne.style.zIndex));

    // ±2 are the second ring: smaller and fainter (per the stylesheet).
    expect(cardAt(container, "2").className).toContain("is-near");
    expect(cardAt(container, "-2").className).toContain("is-near");
    // ...and nothing further out is shown.
    expect(cardAt(container, "3").className).toContain("is-hidden");
    expect(cardAt(container, "3").getAttribute("aria-hidden")).toBe("true");

    expect(cards(container)).toHaveLength(6);
  });

  it("moves the chosen side card to the centre instead of navigating", async () => {
    serveDeals(SIX_DEALS);
    const { container } = renderHome();
    await screen.findByText("کالای اول");

    const side = cardAt(container, "2");
    const sideLink = side.querySelector("a");
    expect(sideLink.getAttribute("href")).toBe("/products/item-3/");

    fireEvent.click(sideLink);

    // It became the centre card -- same DOM node, no navigation.
    expect(centreName(container)).toBe("کالای سوم");
    expect(screen.getByTestId("location").textContent).toBe("/");
    expect(cardAt(container, "0")).toBe(side);
    expect(cardAt(container, "0").className).toContain("is-centre");

    // And the one that was centred moved two slots to the RIGHT (it was two
    // to the left of the chosen card, so the set travelled left by two).
    expect(cardAt(container, "-2").querySelector(".deal-card__name").textContent).toBe("کالای اول");
    expect(cardAt(container, "1").querySelector(".deal-card__name").textContent).toBe("کالای چهارم");
  });

  it("rotates with the arrows, in both directions", async () => {
    serveDeals(THREE_DEALS);
    const { container } = renderHome();
    await screen.findByText("کالای اول");

    fireEvent.click(screen.getByRole("button", { name: "پیشنهاد بعدی" }));
    expect(centreName(container)).toBe("کالای دوم");

    fireEvent.click(screen.getByRole("button", { name: "پیشنهاد قبلی" }));
    expect(centreName(container)).toBe("کالای اول");
  });

  it("wraps around in both directions", async () => {
    serveDeals(THREE_DEALS);
    const { container } = renderHome();
    await screen.findByText("کالای اول");

    // Before the first deal comes the last one.
    fireEvent.click(screen.getByRole("button", { name: "پیشنهاد قبلی" }));
    expect(centreName(container)).toBe("کالای سوم");

    // After the last deal comes the first one.
    fireEvent.click(screen.getByRole("button", { name: "پیشنهاد بعدی" }));
    expect(centreName(container)).toBe("کالای اول");
  });

  it("follows the visual sides with ArrowLeft / ArrowRight", async () => {
    serveDeals(THREE_DEALS);
    const { container } = renderHome();
    await screen.findByText("کالای اول");

    const stage = container.querySelector(".deals-desktop");
    fireEvent.keyDown(stage, { key: "ArrowLeft" });
    expect(centreName(container)).toBe("کالای دوم");
    fireEvent.keyDown(stage, { key: "ArrowRight" });
    expect(centreName(container)).toBe("کالای اول");
  });

  it("marks the rotation so the centre card's text fades in after it arrives", async () => {
    serveDeals(THREE_DEALS);
    const { container } = renderHome();
    await screen.findByText("کالای اول");
    const stage = container.querySelector(".deals-cf__stage");
    expect(stage.className).not.toContain("is-rotating");

    fireEvent.click(screen.getByRole("button", { name: "پیشنهاد بعدی" }));
    expect(stage.className).toContain("is-rotating");
    await waitFor(() => expect(stage.className).not.toContain("is-rotating"), { timeout: 2000 });
  });

  it("swaps instantly under prefers-reduced-motion", async () => {
    window.matchMedia = (query) => ({
      ...originalMatchMedia(query),
      matches: query.includes("prefers-reduced-motion"),
    });
    serveDeals(THREE_DEALS);
    const { container } = renderHome();
    await screen.findByText("کالای اول");

    fireEvent.click(screen.getByRole("button", { name: "پیشنهاد بعدی" }));
    expect(centreName(container)).toBe("کالای دوم");
    // No motion state at all: the set has already switched.
    expect(container.querySelector(".deals-cf__stage").className).not.toContain("is-rotating");
  });

  it("shows a single centre card, no arrows and no sides for one deal", async () => {
    const { container } = renderHome();
    await screen.findByText("پارچ مدل ۱۲۳");

    expect(cards(container)).toHaveLength(1);
    expect(centreName(container)).toBe("پارچ مدل ۱۲۳");
    expect(container.querySelectorAll(".deals-cf__card.is-side")).toHaveLength(0);
    expect(screen.queryByRole("button", { name: "پیشنهاد بعدی" })).toBeNull();
    expect(screen.queryByRole("button", { name: "پیشنهاد قبلی" })).toBeNull();
  });

  it("keeps exactly one side card with two deals", async () => {
    serveDeals(MULTI_DEALS);
    const { container } = renderHome();
    await screen.findByText("کالای اول");

    expect(cards(container)).toHaveLength(2);
    expect(container.querySelectorAll(".deals-cf__card.is-side")).toHaveLength(1);
    expect(cardAt(container, "1").querySelector(".deal-card__name").textContent).toBe("کالای دوم");

    fireEvent.click(cardAt(container, "1").querySelector("a"));
    expect(centreName(container)).toBe("کالای دوم");
    expect(cardAt(container, "1").querySelector(".deal-card__name").textContent).toBe("کالای اول");
  });
});

describe("desktop coverflow auto-advance", () => {
  it("advances every 10 seconds", async () => {
    serveDeals(THREE_DEALS);
    vi.useFakeTimers();
    const { container } = renderHome();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(centreName(container)).toBe("کالای اول");

    await act(async () => {
      await vi.advanceTimersByTimeAsync(9999);
    });
    expect(centreName(container)).toBe("کالای اول");

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1);
    });
    expect(centreName(container)).toBe("کالای دوم");

    await act(async () => {
      await vi.advanceTimersByTimeAsync(10000);
    });
    expect(centreName(container)).toBe("کالای سوم");
  });

  it("pauses on hover and resumes when the pointer leaves", async () => {
    serveDeals(THREE_DEALS);
    vi.useFakeTimers();
    const { container } = renderHome();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    const stage = container.querySelector(".deals-desktop");

    fireEvent.mouseEnter(stage);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(30000);
    });
    expect(centreName(container)).toBe("کالای اول");

    fireEvent.mouseLeave(stage);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10000);
    });
    expect(centreName(container)).toBe("کالای دوم");
  });

  it("never auto-advances a single deal", async () => {
    vi.useFakeTimers();
    const { container } = renderHome();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(centreName(container)).toBe("پارچ مدل ۱۲۳");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(60000);
    });
    expect(centreName(container)).toBe("پارچ مدل ۱۲۳");
  });
});

describe("daily deals discount badge", () => {
  const serveOne = (payload) => {
    serveDeals(payload);
    return renderHome();
  };

  it("floors the percentage instead of rounding it up", async () => {
    serveOne({
      count: 1,
      server_now: SERVER_NOW,
      results: [
        {
          id: 71,
          sale_price: 1,
          starts_at: "2026-10-18T10:00:00.000Z",
          ends_at: "2026-10-18T20:00:00.000Z",
          product: {
            id: 88,
            name: "کالای نزدیک به رایگان",
            slug: "almost-free",
            primary_image: null,
            price_info: { price: 100000, compare_at_price: 99998 },
          },
        },
      ],
    });

    await screen.findByText("کالای نزدیک به رایگان");
    // 99.998% floors to 99 -- it must never read «۱۰۰٪ تخفیف».
    expect(screen.getByText("۹۹٪ تخفیف")).toBeTruthy();
    expect(screen.queryByText("۱۰۰٪ تخفیف")).toBeNull();
  });

  it("never shows 100% even for a free deal price", async () => {
    serveOne({
      count: 1,
      server_now: SERVER_NOW,
      results: [
        {
          id: 72,
          sale_price: 0,
          starts_at: "2026-10-18T10:00:00.000Z",
          ends_at: "2026-10-18T20:00:00.000Z",
          product: {
            id: 89,
            name: "کالای رایگان",
            slug: "free-item",
            primary_image: null,
            price_info: { price: 250000, compare_at_price: 250000 },
          },
        },
      ],
    });

    await screen.findByText("کالای رایگان");
    expect(screen.getByText("۹۹٪ تخفیف")).toBeTruthy();
    expect(screen.queryByText("۱۰۰٪ تخفیف")).toBeNull();
  });
});

describe("phone deal band", () => {
  it("shows the phone band's «مشاهده همه» link and keeps the coverflow out", async () => {
    setViewport(true);
    const { container } = renderHome();
    await screen.findByText("پارچ مدل ۱۲۳");

    const seeAll = screen.getByRole("link", { name: "مشاهده همه" });
    expect(seeAll.getAttribute("href")).toBe("/shop/?on_sale=true");
    expect(container.querySelector(".deals-mobile__all")).toBe(seeAll);
    expect(container.querySelector(".deals-desktop")).toBeNull();
  });

  it("prints «پیشنهاد امروز» once on phones: the band header keeps it, the section h2 hides", async () => {
    // PR 20: the title showed twice on phones (the section's h2 AND the
    // band's own header). The band header (title + «مشاهده همه» + timer)
    // is the one that stays; the section head is display:none at
    // <=767px only.
    setViewport(true);
    const { container } = renderHome();
    await screen.findByText("پارچ مدل ۱۲۳");

    const bandHeader = container.querySelector(".deals-mobile__header");
    expect(bandHeader.querySelector(".deals-mobile__title").textContent).toBe("پیشنهاد امروز");
    expect(within(bandHeader).getByRole("link", { name: "مشاهده همه" })).toBeTruthy();
    expect(bandHeader.querySelector(".countdown")).toBeTruthy();

    expect(CSS).toContain("@media (max-width: 767px) { .section--dark .section__head { display: none; } }");
  });
});

describe("coverflow stylesheet", () => {
  it("moves every card with one 600ms transform/opacity/blur transition", () => {
    expect(CSS).toMatch(
      /\.deals-cf__card \{[^}]*transform: translate\(-50%, -50%\) translateX\(calc\(var\(--cf-dx, 0\) \* 1%\)\) scale\(var\(--cf-scale, 1\)\)/
    );
    expect(CSS).toMatch(
      /\.deals-cf__card \{[^}]*transition: transform 600ms ease-in-out, opacity 600ms ease-in-out, filter 600ms ease-in-out/
    );
    expect(CSS).toMatch(/\.deals-cf__card \{[^}]*opacity: var\(--cf-opacity, 1\)/);
    expect(CSS).toMatch(/\.deals-cf__card \{[^}]*filter: blur\(var\(--cf-blur, 0px\)\)/);
    // Fixed-height stage: no layout shift while the set rotates.
    expect(CSS).toMatch(/\.deals-cf__stage \{[^}]*height: var\(--deals-cf-height\)/);
  });

  it("fades the centre card's text in only after it has arrived", () => {
    expect(CSS).toMatch(
      /\.deals-cf__stage\.is-rotating \.deals-cf__card\.is-centre \.deal-card__name[^{]*\{[^}]*animation: deals-cf-text-in 240ms ease-out 400ms both/
    );
    expect(CSS).toMatch(/@keyframes deals-cf-text-in \{[^}]*translateY\(6px\)/);
  });

  it("drops the motion under prefers-reduced-motion", () => {
    expect(CSS).toMatch(
      /@media \(prefers-reduced-motion: reduce\) \{[^@]*?\.deals-cf__card \{ transition: none; \}/
    );
  });

  it("keeps the phone band's card width untouched", () => {
    expect(CSS).toMatch(/\.deals-mobile__card \{[^}]*flex: 0 0 45vw/);
    expect(CSS).toMatch(/\.deals-mobile__all \{/);
  });
});
