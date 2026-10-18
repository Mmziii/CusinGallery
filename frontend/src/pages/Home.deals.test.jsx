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
});
