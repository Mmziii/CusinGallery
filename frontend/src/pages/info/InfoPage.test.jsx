import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";

import InfoPage from "./InfoPage";
import apiClient from "../../services/apiClient";

const originalAdapter = apiClient.defaults.adapter;

function notFound(config) {
  return {
    response: { status: 404, data: { detail: "این صفحه وجود ندارد یا منتشر نشده است." } },
    config,
    isAxiosError: true,
  };
}

afterEach(() => {
  cleanup();
  apiClient.defaults.adapter = originalAdapter;
});

describe("owner-editable info pages (Task 3)", () => {
  it("renders the sanitised body and the page's SEO metadata", async () => {
    apiClient.defaults.adapter = async (config) => {
      if ((config.url || "") === "/site/pages/shipping-returns/") {
        return {
          data: {
            slug: "shipping-returns",
            path: "/shipping-returns/",
            title: "ارسال و مرجوعی",
            body:
              "<h2>ارسال</h2><p>ارسال با پست پیشتاز انجام می‌شود.</p>" +
              '<ul><li>بسته‌بندی ضدضربه</li></ul><p><a href="/contact/">تماس با ما</a></p>',
            seo_title: "ارسال و مرجوعی | راهنمای خرید",
            seo_description: "شرایط ارسال و بازگشت کالا در فروشگاه.",
            updated_at: "2026-10-18T10:00:00+00:00",
          },
          status: 200,
          statusText: "OK",
          headers: {},
          config,
        };
      }
      return originalAdapter(config);
    };

    const { container } = render(
      <MemoryRouter>
        <InfoPage slug="shipping-returns" path="/shipping-returns/" />
      </MemoryRouter>
    );

    expect(await screen.findByRole("heading", { name: "ارسال و مرجوعی", level: 1 })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "ارسال", level: 2 })).toBeTruthy();
    expect(screen.getByText("ارسال با پست پیشتاز انجام می‌شود.")).toBeTruthy();
    expect(screen.getByText("بسته‌بندی ضدضربه")).toBeTruthy();
    expect(screen.getByRole("link", { name: "تماس با ما" }).getAttribute("href")).toBe(
      "/contact/"
    );
    expect(container.querySelector(".rich-text")).not.toBeNull();
    await waitFor(() => {
      expect(document.title).toBe("ارسال و مرجوعی | راهنمای خرید | کازین گالری");
    });
    expect(
      document.head.querySelector('meta[name="description"]').getAttribute("content")
    ).toBe("شرایط ارسال و بازگشت کالا در فروشگاه.");
    expect(document.head.querySelector('link[rel="canonical"]').getAttribute("href")).toBe(
      "https://cusin.ir/shipping-returns/"
    );
  });

  it("shows the 404 view when the page is unpublished", async () => {
    apiClient.defaults.adapter = async (config) => {
      if ((config.url || "") === "/site/pages/terms/") {
        throw notFound(config);
      }
      return originalAdapter(config);
    };

    render(
      <MemoryRouter>
        <InfoPage slug="terms" path="/terms/" />
      </MemoryRouter>
    );

    expect(await screen.findByText("۴۰۴", { selector: "h1" })).toBeTruthy();
    expect(screen.getByText(/صفحه مورد نظر پیدا نشد/)).toBeTruthy();
    await waitFor(() => {
      expect(
        document.head.querySelector('meta[name="robots"]').getAttribute("content")
      ).toBe("noindex, nofollow");
    });
  });

  it("offers a retry on a real server failure instead of pretending it is a 404", async () => {
    let attempts = 0;
    apiClient.defaults.adapter = async (config) => {
      if ((config.url || "") === "/site/pages/about/") {
        attempts += 1;
        if (attempts === 1) {
          throw Object.assign(new Error("boom"), {
            response: { status: 500, data: { detail: "boom" } },
            config,
          });
        }
        return {
          data: { slug: "about", path: "/about/", title: "دربارهٔ ما", body: "<p>متن</p>" },
          status: 200,
          statusText: "OK",
          headers: {},
          config,
        };
      }
      return originalAdapter(config);
    };

    const { container } = render(
      <MemoryRouter>
        <InfoPage slug="about" path="/about/" />
      </MemoryRouter>
    );

    expect(await screen.findByRole("button", { name: "تلاش دوباره" })).toBeTruthy();
    expect(container.querySelector(".rich-text")).toBeNull();
  });
});
