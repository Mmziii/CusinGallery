import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import Home from "./Home";
import apiClient from "../services/apiClient";
import { resetSiteContentCache } from "../services/siteApi";

const originalAdapter = apiClient.defaults.adapter;

const CONTENT = {
  brand: { name: "کازین گالری", tagline: "", logo_light: "", logo_dark: "", favicon: "" },
  home: {
    heading: "فروشگاه خانهٔ ما",
    hero: {
      title: "به خانهٔ ما خوش آمدید",
      subtitle: "ظروف دست‌چین برای هر آشپزخانه",
      button_text: "همین حالا ببینید",
      button_link: "/shop/",
    },
    sections: {
      categories: "دسته‌های ما",
      deals: "تخفیف‌های امروز",
      featured: "انتخاب سردبیر",
      new: "تازه رسیده‌ها",
      best_sellers: "محبوب‌ترین‌ها",
      reviews: "نظر خریداران",
    },
    story: { title: "داستان ما", text: "متنی که مدیر فروشگاه نوشته است." },
  },
  trust_strip: [{ icon: "truck", label: "ارسال رایگان برای سفارش‌های بزرگ" }],
  footer: {},
  floating: { enabled: true, links: [], show_scroll_top: true },
  theme: null,
  info_pages: [],
};

const CATEGORY_ROOT = {
  id: 1,
  name: "آشپزخانه",
  slug: "kitchen",
  is_catalog_root: true,
  children: [{ id: 2, name: "ظروف پخت", slug: "cookware", children: [] }],
};
const PRODUCT = {
  id: 42,
  name: "پارچ نمونه",
  slug: "sample-pitcher",
  primary_image: null,
  price_info: { price: 100000, compare_at_price: null, is_on_sale: false },
};
const DEAL = {
  id: 7,
  sale_price: 85000,
  starts_at: "2026-10-18T11:00:00.000Z",
  ends_at: "2026-10-18T15:00:00.000Z",
  product: PRODUCT,
};

function serveContent(payload) {
  apiClient.defaults.adapter = async (config) => {
    const url = config.url || "";
    if (url === "/site/content/") {
      return { data: payload, status: 200, statusText: "OK", headers: {}, config };
    }
    if (url === "/categories/tree/") {
      return {
        data: { count: 1, next: null, previous: null, results: [CATEGORY_ROOT] },
        status: 200, statusText: "OK", headers: {}, config,
      };
    }
    if (url === "/products/") {
      return {
        data: { count: 1, next: null, previous: null, results: [PRODUCT] },
        status: 200, statusText: "OK", headers: {}, config,
      };
    }
    if (url === "/banners/daily-deals/") {
      return {
        data: { count: 1, next: null, previous: null, server_now: "2026-10-18T12:00:00.000Z", results: [DEAL] },
        status: 200, statusText: "OK", headers: {}, config,
      };
    }
    if (url.startsWith("/reviews/product/")) {
      return {
        data: { count: 1, next: null, previous: null, results: [{ id: 1, body: "کیفیت عالی بود", rating: 5 }] },
        status: 200, statusText: "OK", headers: {}, config,
      };
    }
    if (url === "/banners/") {
      return {
        data: { count: 0, next: null, previous: null, results: [] },
        status: 200, statusText: "OK", headers: {}, config,
      };
    }
    return originalAdapter(config);
  };
}

beforeEach(() => {
  resetSiteContentCache();
});

afterEach(() => {
  cleanup();
  resetSiteContentCache();
  apiClient.defaults.adapter = originalAdapter;
});

describe("homepage owner content (Task 3)", () => {
  it("renders the owner's trust strip, section titles, hero copy and story", async () => {
    serveContent(CONTENT);
    render(
      <MemoryRouter>
        <Home />
      </MemoryRouter>
    );

    expect(await screen.findByText("ارسال رایگان برای سفارش‌های بزرگ")).toBeTruthy();
    expect(await screen.findByText("دسته‌های ما")).toBeTruthy();
    expect(screen.getByText("تخفیف‌های امروز")).toBeTruthy();
    expect(screen.getByText("انتخاب سردبیر")).toBeTruthy();
    expect(screen.getByText("تازه رسیده‌ها")).toBeTruthy();
    expect(screen.getByText("محبوب‌ترین‌ها")).toBeTruthy();
    expect(screen.getByText("نظر خریداران")).toBeTruthy();

    // No banners in this test: the owner's hero copy is the hero.
    expect(screen.getByRole("heading", { name: "به خانهٔ ما خوش آمدید" })).toBeTruthy();
    expect(screen.getByText("ظروف دست‌چین برای هر آشپزخانه")).toBeTruthy();
    const cta = screen.getByRole("link", { name: "همین حالا ببینید" });
    expect(cta.getAttribute("href")).toBe("/shop/");

    expect(screen.getByRole("heading", { name: "داستان ما" })).toBeTruthy();
    expect(screen.getByText("متنی که مدیر فروشگاه نوشته است.")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "فروشگاه خانهٔ ما", level: 1 })).toBeTruthy();
  });

  it("hides the trust strip when the owner hides every item", async () => {
    serveContent({ ...CONTENT, trust_strip: [] });
    const { container } = render(
      <MemoryRouter>
        <Home />
      </MemoryRouter>
    );
    await screen.findByText("داستان ما");
    expect(container.querySelectorAll(".trust-strip__item")).toHaveLength(0);
  });

  it("falls back to the current texts when the API fails", async () => {
    apiClient.defaults.adapter = async (config) => {
      if ((config.url || "") === "/site/content/") {
        throw Object.assign(new Error("offline"), { response: { status: 503, data: {} } });
      }
      return originalAdapter(config);
    };
    render(
      <MemoryRouter>
        <Home />
      </MemoryRouter>
    );
    expect(
      await screen.findByText("تضمین اصالت کالا و سلامت فیزیکی اجناس")
    ).toBeTruthy();
    expect(screen.getByText("کازین گالری؛ خانهٔ ظروف دوست‌داشتنی", { selector: "h2" })).toBeTruthy();
  });
});
