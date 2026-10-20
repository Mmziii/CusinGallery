import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import Footer from "./Footer";
import apiClient from "../services/apiClient";
import { resetSiteContentCache } from "../services/siteApi";

const originalAdapter = apiClient.defaults.adapter;

const CONTENT = {
  brand: { name: "گالری نمونه", tagline: "ظروف خوب برای خانه" },
  home: {},
  trust_strip: [],
  footer: {
    about: "دربارهٔ فروشگاه به قلم مدیر.",
    phones: ["021-12345678", "۰۹۱۲۰۰۰۰۰۰۰"],
    email: "hello@example.com",
    address: "تهران، خیابان نمونه، پلاک 46",
    working_hours: "شنبه تا پنجشنبه، 10:00-21:00",
    socials: {
      instagram: "https://instagram.com/cusin",
      telegram: "https://t.me/cusin",
    },
    enamad_html:
      '<a href="https://trustseal.enamad.ir/?id=1"><img src="https://trustseal.enamad.ir/logo.png" alt="نماد اعتماد"></a>',
    copyright_text: "© {year} گالری نمونه — همهٔ حقوق محفوظ است",
    quick_links_title: "دسترسی سریع ما",
    help_links_title: "قوانین ما",
    trust_title: "مجوزهای ما",
  },
  floating: { enabled: true, links: [], show_scroll_top: true },
  theme: null,
  info_pages: [
    { slug: "about", path: "/about/", title: "دربارهٔ ما" },
    { slug: "privacy", path: "/privacy/", title: "حریم خصوصی" },
  ],
};

function serveContent(payload) {
  apiClient.defaults.adapter = async (config) => {
    if ((config.url || "") === "/site/content/") {
      return { data: payload, status: 200, statusText: "OK", headers: {}, config };
    }
    return originalAdapter(config);
  };
}

function renderFooter() {
  return render(
    <MemoryRouter>
      <Footer />
    </MemoryRouter>
  );
}

beforeEach(() => resetSiteContentCache());
afterEach(() => {
  cleanup();
  resetSiteContentCache();
  apiClient.defaults.adapter = originalAdapter;
});

describe("footer owner content (Task 3)", () => {
  it("renders brand, about, contact details, hours and socials from the API", async () => {
    serveContent(CONTENT);
    const { container } = renderFooter();

    expect(await screen.findByRole("heading", { name: "گالری نمونه" })).toBeTruthy();
    expect(screen.getByText("ظروف خوب برای خانه")).toBeTruthy();
    expect(screen.getByText("دربارهٔ فروشگاه به قلم مدیر.")).toBeTruthy();
    expect(screen.getByText("تهران، خیابان نمونه، پلاک ۴۶")).toBeTruthy();
    expect(screen.getByText("ساعات پاسخگویی: شنبه تا پنجشنبه، ۱۰:۰۰ تا ۲۱:۰۰")).toBeTruthy();
    expect(screen.getByRole("link", { name: /۰۲۱-۱۲۳۴۵۶۷۸/ }).textContent).toBe("۰۲۱-۱۲۳۴۵۶۷۸");
    expect(screen.getByRole("link", { name: /۰۲۱-۱۲۳۴۵۶۷۸/ }).getAttribute("href")).toBe(
      "tel:021-12345678"
    );
    expect(screen.getByRole("link", { name: "۰۹۱۲۰۰۰۰۰۰۰" }).getAttribute("href")).toBe("tel:09120000000");
    expect(screen.getByRole("link", { name: /hello@example.com/ }).getAttribute("href")).toBe(
      "mailto:hello@example.com"
    );
    expect(
      screen.getByRole("link", { name: "اینستاگرام" }).getAttribute("href")
    ).toBe("https://instagram.com/cusin");
    expect(screen.getByRole("link", { name: "تلگرام" }).getAttribute("href")).toBe(
      "https://t.me/cusin"
    );
    expect(container.querySelectorAll(".site-footer__social a")).toHaveLength(2);
  });

  it("renders the sanitised e-namad embed, the copyright and only published pages", async () => {
    serveContent(CONTENT);
    const { container } = renderFooter();

    await screen.findByRole("heading", { name: "گالری نمونه" });
    const embed = container.querySelector(".site-footer__enamad-embed");
    expect(embed.querySelector("a").getAttribute("href")).toBe(
      "https://trustseal.enamad.ir/?id=1"
    );
    expect(screen.getByText(/گالری نمونه — همهٔ حقوق محفوظ است/)).toBeTruthy();

    expect(screen.getByRole("heading", { name: "قوانین ما" })).toBeTruthy();
    const helpLinks = [...container.querySelectorAll(".site-footer__grid > div:nth-child(3) a")];
    expect(helpLinks.map((link) => link.textContent)).toEqual(["دربارهٔ ما", "حریم خصوصی"]);
    expect(container.querySelector('a[href="/terms/"]')).toBeNull();
  });

  it("keeps the historical help links when the API is unreachable", async () => {
    const { container } = renderFooter();
    expect(await screen.findByText("کازین گالری")).toBeTruthy();
    const helpLinks = [...container.querySelectorAll(".site-footer__grid > div:nth-child(3) a")];
    expect(helpLinks.map((link) => link.getAttribute("href"))).toEqual([
      "/about/",
      "/contact/",
      "/shipping-returns/",
      "/terms/",
      "/privacy/",
    ]);
  });
});
