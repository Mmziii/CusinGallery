import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import Header from "./Header.jsx";
import apiClient from "../services/apiClient";
import { resetSiteContentCache } from "../services/siteApi";

const originalAdapter = apiClient.defaults.adapter;

beforeEach(() => {
  resetSiteContentCache();
  apiClient.defaults.adapter = async (config) => {
    if ((config.url || "") === "/site/content/") {
      return {
        data: {
          brand: {
            name: "گالری خانهٔ ما",
            tagline: "ظروف دست‌چین",
            logo_light: "/media/brand/logo-light.png",
            logo_dark: "",
            favicon: "",
          },
          home: {},
          trust_strip: [],
          footer: {},
          floating: { enabled: true, links: [], show_scroll_top: true },
          theme: null,
          info_pages: [],
        },
        status: 200,
        statusText: "OK",
        headers: {},
        config,
      };
    }
    return originalAdapter(config);
  };
});

afterEach(() => {
  cleanup();
  resetSiteContentCache();
  apiClient.defaults.adapter = originalAdapter;
});

describe("header brand from the owner content API (Task 3)", () => {
  it("uses the uploaded name and logo, and keeps the accessible home label", async () => {
    render(
      <MemoryRouter>
        <Header />
      </MemoryRouter>
    );

    const brandLinks = await screen.findAllByRole("link", { name: "گالری خانهٔ ما — صفحه اصلی" });
    expect(brandLinks.length).toBeGreaterThan(0);
    const logo = brandLinks[0].querySelector("img");
    expect(logo.getAttribute("src")).toBe("/media/brand/logo-light.png");
    expect(brandLinks[0].getAttribute("href")).toBe("/");
  });

  it("falls back to the bundled mark when the API is unavailable", async () => {
    apiClient.defaults.adapter = async (config) => {
      if ((config.url || "") === "/site/content/") {
        throw Object.assign(new Error("offline"), { response: { status: 500, data: {} } });
      }
      return originalAdapter(config);
    };
    render(
      <MemoryRouter>
        <Header />
      </MemoryRouter>
    );
    const brandLinks = await screen.findAllByRole("link", { name: "کازین گالری — صفحه اصلی" });
    expect(brandLinks[0].querySelector("img").getAttribute("src")).toBe(
      "/brand/logo-gold.svg"
    );
  });
});
