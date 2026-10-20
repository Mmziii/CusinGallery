import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

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
    {
      id: 1,
      sale_price: 50000,
      starts_at: "2026-10-18T10:00:00.000Z",
      ends_at: "2026-10-18T18:00:00.000Z",
      product: {
        id: 101,
        name: "کالای اول",
        slug: "item-1",
        primary_image: { image: "/img1.jpg", alt_text: "کالا ۱" },
        price_info: { price: 100000 },
      },
    },
    {
      id: 2,
      sale_price: 70000,
      starts_at: "2026-10-18T10:00:00.000Z",
      ends_at: "2026-10-18T18:00:00.000Z",
      product: {
        id: 102,
        name: "کالای دوم",
        slug: "item-2",
        primary_image: { image: "/img2.jpg", alt_text: "کالا ۲" },
        price_info: { price: 100000 },
      },
    },
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

beforeEach(() => {
  serveDeals(DAILY_DEAL);
});

afterEach(() => {
  cleanup();
  apiClient.defaults.adapter = originalAdapter;
  window.matchMedia = originalMatchMedia;
});

describe("homepage daily deal", () => {
  it("renders the actual deal discount, old price, Persian name and labeled Persian countdown", async () => {
    const { container } = render(
      <MemoryRouter>
        <Home />
      </MemoryRouter>
    );

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

  it("handles carousel prev/next and thumbnail clicks with multiple deals", async () => {
    serveDeals(MULTI_DEALS);

    const { container } = render(
      <MemoryRouter>
        <Home />
      </MemoryRouter>
    );

    const firstName = await screen.findByText("کالای اول");
    expect(firstName).toBeTruthy();

    const nextBtn = screen.getByRole("button", { name: "پیشنهاد بعدی" });
    nextBtn.click();

    const secondName = await screen.findByText("کالای دوم");
    expect(secondName).toBeTruthy();

    const thumbs = container.querySelectorAll(".deals-thumb");
    expect(thumbs.length).toBe(2);
    thumbs[0].click();

    expect(await screen.findByText("کالای اول")).toBeTruthy();
  });

  it("does not render deals section when all deals are expired", async () => {
    const EXPIRED_DEALS = {
      count: 1,
      server_now: SERVER_NOW,
      results: [
        {
          id: 99,
          sale_price: 50000,
          starts_at: "2026-10-18T08:00:00.000Z",
          ends_at: "2026-10-18T10:00:00.000Z", // before server_now (12:00)
          product: {
            id: 999,
            name: "کالای منقضی",
            slug: "expired-item",
            price_info: { price: 100000 },
          },
        },
      ],
    };

    apiClient.defaults.adapter = async (config) => {
      if ((config.url || "").includes("/banners/daily-deals/")) {
        return { data: EXPIRED_DEALS, status: 200, statusText: "OK", headers: {}, config };
      }
      return originalAdapter(config);
    };

    const { container } = render(
      <MemoryRouter>
        <Home />
      </MemoryRouter>
    );

    // Wait a tick for any async state to settle
    await new Promise((r) => setTimeout(r, 50));
    expect(screen.queryByText("کالای منقضی")).toBeNull();
    expect(container.querySelector(".deals-section")).toBeNull();
  });

  it("renders struck compare_at_price and correct percentage when price_info.price equals sale_price", async () => {
    const DEAL_WITH_COMPARE_AT = {
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
            price_info: {
              price: 199000,
              compare_at_price: 240000,
            },
          },
        },
      ],
    };

    apiClient.defaults.adapter = async (config) => {
      if ((config.url || "").includes("/banners/daily-deals/")) {
        return { data: DEAL_WITH_COMPARE_AT, status: 200, statusText: "OK", headers: {}, config };
      }
      return originalAdapter(config);
    };

    const { container } = render(
      <MemoryRouter>
        <Home />
      </MemoryRouter>
    );

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

describe("daily deals slide transition", () => {
  const renderMulti = async () => {
    serveDeals(MULTI_DEALS);
    const { container } = render(
      <MemoryRouter>
        <Home />
      </MemoryRouter>
    );
    await screen.findByText("کالای اول");
    return container;
  };

  const slides = (container) => container.querySelectorAll(".deals-slide");

  it("cross-fades the outgoing slide with the incoming one, then drops it", async () => {
    const container = await renderMulti();
    expect(slides(container)).toHaveLength(1);

    fireEvent.click(screen.getByRole("button", { name: "پیشنهاد بعدی" }));

    // Both slides are on screen at once: the old one leaving, the new one
    // entering -- which is what makes it a transition instead of a swap.
    expect(slides(container)).toHaveLength(2);
    expect(container.querySelector(".deals-slide--out").getAttribute("aria-hidden")).toBe("true");
    expect(container.querySelector(".deals-slide--in").textContent).toContain("کالای دوم");

    // Forward travel: the new slide comes in from the right (dir = 1).
    const stage = container.querySelector(".deals-slides");
    expect(stage.style.getPropertyValue("--deals-dir")).toBe("1");

    // ... and the outgoing slide is gone once the animation has played.
    await waitFor(() => expect(slides(container)).toHaveLength(1), { timeout: 2000 });
    expect(container.querySelector(".deals-slide--in")).toBeNull();
  });

  it("slides the other way when going back", async () => {
    const container = await renderMulti();
    fireEvent.click(screen.getByRole("button", { name: "پیشنهاد بعدی" }));
    await screen.findByText("کالای دوم");

    fireEvent.click(screen.getByRole("button", { name: "پیشنهاد قبلی" }));
    expect(container.querySelector(".deals-slides").style.getPropertyValue("--deals-dir")).toBe("-1");
    expect(container.querySelector(".deals-slide--in").textContent).toContain("کالای اول");
  });

  it("moves the thumbnail highlight to the selected deal", async () => {
    const container = await renderMulti();
    const thumbs = container.querySelector(".deals-thumbs");
    expect(thumbs.style.getPropertyValue("--deals-thumb-index")).toBe("0");
    // The highlight lives inside the track -- the element that is exactly as
    // wide as the thumbnails, so its offset lands on the right thumb however
    // wide the centring container is.
    const highlight = thumbs.querySelector(".deals-thumbs__track .deals-thumbs__highlight");
    expect(highlight).toBeTruthy();

    fireEvent.click(container.querySelectorAll(".deals-thumb")[1]);
    await screen.findByText("کالای دوم");
    expect(thumbs.style.getPropertyValue("--deals-thumb-index")).toBe("1");
  });

  it("swaps instantly under prefers-reduced-motion", async () => {
    window.matchMedia = (query) => ({
      ...originalMatchMedia(query),
      matches: query.includes("prefers-reduced-motion"),
    });
    const container = await renderMulti();

    fireEvent.click(screen.getByRole("button", { name: "پیشنهاد بعدی" }));
    await screen.findByText("کالای دوم");

    expect(slides(container)).toHaveLength(1);
    expect(container.querySelector(".deals-slide--out")).toBeNull();
  });

  it("shows the phone band's «مشاهده همه» link and ~2.2 cards per screen", async () => {
    setViewport(true);
    const { container } = render(
      <MemoryRouter>
        <Home />
      </MemoryRouter>
    );
    await screen.findByText("پارچ مدل ۱۲۳");

    const seeAll = screen.getByRole("link", { name: "مشاهده همه" });
    expect(seeAll.getAttribute("href")).toBe("/shop/?on_sale=true");
    expect(container.querySelector(".deals-mobile__all")).toBe(seeAll);

    // The phone band keeps the carousel markup out of the way.
    expect(container.querySelector(".deals-desktop")).toBeNull();
  });
});

describe("daily deals discount badge", () => {
  const serveOne = (payload) => {
    serveDeals(payload);
    return render(
      <MemoryRouter>
        <Home />
      </MemoryRouter>
    );
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

    const dealName = await screen.findByText("کالای نزدیک به رایگان");
    expect(dealName).toBeTruthy();
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

describe("daily deals transition stylesheet", () => {
  it("fades + slides the incoming slide for ~450ms ease-out with a staggered body", () => {
    expect(CSS).toMatch(/\.deals-slides \{[^}]*grid-template-areas: "slide"/);
    expect(CSS).toMatch(/\.deals-slide \{[^}]*grid-area: slide/);
    expect(CSS).toMatch(/\.deals-slide--in \{[^}]*animation: deals-slide-in 450ms ease-out both/);
    expect(CSS).toMatch(/\.deals-slide--out \{[^}]*animation: deals-slide-out 450ms ease-out both/);
    expect(CSS).toMatch(/@keyframes deals-slide-in \{[^}]*translateX\(calc\(var\(--deals-dir, 1\) \* 14px\)\)/);
    expect(CSS).toMatch(/@keyframes deals-media-in \{[^}]*scale\(\.98\)/);
    expect(CSS).toMatch(/\.deals-slide--in \.deal-card__name \{[^}]*deals-rise 320ms ease-out 70ms both/);
    expect(CSS).toMatch(/\.deals-slide--in \.deal-card__prices \{[^}]*deals-rise 320ms ease-out 140ms both/);
    expect(CSS).toMatch(/\.deals-slide--in \.deal-card__cta \{[^}]*deals-rise 320ms ease-out 210ms both/);
    expect(CSS).toMatch(/\.deals-thumbs__highlight \{[^}]*transition: inset-inline-start \.3s ease-out/);
  });

  it("drops every deal animation under prefers-reduced-motion", () => {
    expect(CSS).toMatch(
      /@media \(prefers-reduced-motion: reduce\) \{[^@]*?\.deals-slide--in, \.deals-slide--out,[^}]*\{[^}]*animation: none/
    );
  });

  it("shows a bit over two deal cards on a phone (45vw)", () => {
    expect(CSS).toMatch(/\.deals-mobile__card \{[^}]*flex: 0 0 45vw/);
    expect(CSS).toMatch(/\.deals-mobile__all \{/);
  });
});
