import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import FloatingContact from "./FloatingContact";
import apiClient from "../services/apiClient";
import { resetSiteContentCache, resetSiteSettingsCache } from "../services/siteApi";

const originalAdapter = apiClient.defaults.adapter;

function serve({ content, settings }, config) {
  const url = config.url || "";
  if (url === "/site/content/" && content) {
    return { data: content, status: 200, statusText: "OK", headers: {}, config };
  }
  if (url === "/site/settings/" && settings) {
    return { data: settings, status: 200, statusText: "OK", headers: {}, config };
  }
  return originalAdapter(config);
}

function withContent(floating) {
  return {
    brand: { name: "کازین گالری" },
    home: {},
    trust_strip: [],
    footer: {},
    floating,
    theme: null,
    info_pages: [],
  };
}

function renderAt(path = "/") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <FloatingContact />
    </MemoryRouter>
  );
}

beforeEach(() => {
  resetSiteContentCache();
  resetSiteSettingsCache();
});
afterEach(() => {
  cleanup();
  resetSiteContentCache();
  resetSiteSettingsCache();
  apiClient.defaults.adapter = originalAdapter;
});

describe("floating contact buttons (Task 3)", () => {
  it("renders exactly the channels the owner enabled, with safe URLs", async () => {
    apiClient.defaults.adapter = async (config) =>
      serve(
        {
          content: withContent({
            enabled: true,
            links: [
              { key: "whatsapp", href: "https://wa.me/989120000000", icon: "chat", label: "گفتگو در واتس‌اپ" },
              { key: "instagram", href: "https://instagram.com/cusin", icon: "instagram", label: "صفحهٔ اینستاگرام" },
            ],
            show_scroll_top: true,
          }),
        },
        config
      );
    const { container } = renderAt();
    const links = await screen.findAllByRole("link");
    expect(links.map((link) => link.getAttribute("href"))).toEqual([
      "https://wa.me/989120000000",
      "https://instagram.com/cusin",
    ]);
    links.forEach((link) => {
      expect(link.getAttribute("target")).toBe("_blank");
      expect(link.getAttribute("rel")).toBe("noopener noreferrer");
    });
    expect(container.querySelectorAll(".floating-contact > a")).toHaveLength(2);
  });

  it("hides contact buttons on cart and checkout and exposes a mobile expander elsewhere", async () => {
    apiClient.defaults.adapter = async (config) =>
      serve({
        content: withContent({ enabled: true, links: [
          { key: "phone", href: "tel:09120000000", icon: "phone", label: "تماس تلفنی" },
          { key: "telegram", href: "https://t.me/cusin", icon: "send", label: "پیام در تلگرام" },
        ] }),
      }, config);
    const cartView = renderAt("/cart/");
    await new Promise((resolve) => setTimeout(resolve, 10));
    expect(cartView.container.querySelector(".floating-contact")).toBeNull();
    cartView.unmount();
    const checkoutView = renderAt("/checkout/");
    await new Promise((resolve) => setTimeout(resolve, 10));
    expect(checkoutView.container.querySelector(".floating-contact")).toBeNull();
    checkoutView.unmount();

    const { container } = renderAt("/shop/");
    const toggle = await screen.findByRole("button", { name: "نمایش راه‌های تماس" });
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    fireEvent.click(toggle);
    expect(screen.getByRole("button", { name: "بستن راه‌های تماس" }).getAttribute("aria-expanded")).toBe("true");
    expect(container.querySelectorAll(".floating-contact > a")).toHaveLength(2);
  });

  it("renders nothing when the owner turned the cluster off", async () => {
    apiClient.defaults.adapter = async (config) =>
      serve({ content: withContent({ enabled: false, links: [], show_scroll_top: true }) }, config);
    const { container } = renderAt();
    // Give the request a tick to resolve; the cluster must stay absent.
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(container.querySelector(".floating-contact")).toBeNull();
  });

  it("falls back to SiteSettings-derived buttons for an older payload", async () => {
    apiClient.defaults.adapter = async (config) =>
      serve(
        {
          content: withContent({ enabled: true, links: null, show_scroll_top: true }),
          settings: { phone: "021-1234", whatsapp: "989120000000", telegram: "@cusin" },
        },
        config
      );
    renderAt();
    const links = await screen.findAllByRole("link");
    expect(links.map((link) => link.getAttribute("href"))).toEqual([
      "https://wa.me/989120000000",
      "https://t.me/cusin",
      "tel:021-1234",
    ]);
  });
});
