import { cleanup, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import apiClient from "../services/apiClient";
import Home from "./Home";

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

beforeEach(() => {
  apiClient.defaults.adapter = async (config) => {
    if ((config.url || "").includes("/banners/daily-deals/")) {
      return { data: DAILY_DEAL, status: 200, statusText: "OK", headers: {}, config };
    }
    return originalAdapter(config);
  };
});

afterEach(() => {
  cleanup();
  apiClient.defaults.adapter = originalAdapter;
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

    apiClient.defaults.adapter = async (config) => {
      if ((config.url || "").includes("/banners/daily-deals/")) {
        return { data: MULTI_DEALS, status: 200, statusText: "OK", headers: {}, config };
      }
      return originalAdapter(config);
    };

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
