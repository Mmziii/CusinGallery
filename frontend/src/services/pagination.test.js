import { afterEach, describe, expect, it } from "vitest";

import { listAddresses } from "./authApi";
import apiClient from "./apiClient";
import { listAllProducts } from "./catalogApi";
import { fetchAllPagesAsEnvelope } from "./pagination";

const originalAdapter = apiClient.defaults.adapter;

const ok = (data, config) => ({ data, status: 200, statusText: "OK", headers: {}, config });

afterEach(() => {
  apiClient.defaults.adapter = originalAdapter;
});

describe("collection pagination service", () => {
  it("normalizes the real DRF envelope and follows next until every row is loaded", async () => {
    const requests = [];
    apiClient.defaults.adapter = async (config) => {
      requests.push(config.url);
      if (config.url === "/accounts/addresses/") {
        return ok(
          {
            count: 3,
            next: "/accounts/addresses/?page=2",
            previous: null,
            results: [{ id: 1 }, { id: 2 }],
          },
          config
        );
      }
      if (config.url === "/accounts/addresses/?page=2") {
        return ok(
          {
            count: 3,
            next: null,
            previous: "/accounts/addresses/",
            results: [{ id: 3 }],
          },
          config
        );
      }
      throw new Error(`unexpected URL ${config.url}`);
    };

    const addresses = await listAddresses();

    expect(addresses).toEqual([{ id: 1 }, { id: 2 }, { id: 3 }]);
    expect(requests).toEqual(["/accounts/addresses/", "/accounts/addresses/?page=2"]);
  });

  it("lets listAddresses accept a legacy bare array during a rolling deployment", async () => {
    apiClient.defaults.adapter = async (config) => {
      expect(config.url).toBe("/accounts/addresses/");
      return ok([{ id: 7 }], config);
    };

    await expect(listAddresses()).resolves.toEqual([{ id: 7 }]);
  });

  it("loads every product page for a cart-sized id set even after the API caps page_size", async () => {
    const ids = Array.from({ length: 101 }, (_, index) => index + 1).join(",");
    const nextUrl = `/products/?ids=${encodeURIComponent(ids)}&page_size=101&page=2`;
    const firstPage = Array.from({ length: 100 }, (_, index) => ({ id: index + 1 }));
    apiClient.defaults.adapter = async (config) => {
      if (config.url === "/products/") {
        expect(config.params).toEqual({ ids, page_size: 101 });
        return ok(
          {
            count: 101,
            next: nextUrl,
            previous: null,
            results: firstPage,
          },
          config
        );
      }
      if (config.url === nextUrl) {
        return ok(
          {
            count: 101,
            next: null,
            previous: `/products/?ids=${encodeURIComponent(ids)}&page_size=101`,
            results: [{ id: 101 }],
          },
          config
        );
      }
      throw new Error(`unexpected URL ${config.url}`);
    };

    const data = await listAllProducts({ ids, page_size: 101 });

    expect(data).toMatchObject({ count: 101, next: null, previous: null });
    expect(data.results).toHaveLength(101);
    expect(data.results[data.results.length - 1]).toEqual({ id: 101 });
  });

  it("keeps metadata fields such as the server clock while flattening page results", async () => {
    apiClient.defaults.adapter = async (config) => {
      if (config.url === "/banners/daily-deals/") {
        return ok(
          {
            count: 2,
            next: "/banners/daily-deals/?page=2",
            previous: null,
            server_now: "2026-10-09T10:00:00+03:30",
            results: [{ id: 1 }],
          },
          config
        );
      }
      return ok(
        {
          count: 2,
          next: null,
          previous: "/banners/daily-deals/",
          results: [{ id: 2 }],
        },
        config
      );
    };

    const data = await fetchAllPagesAsEnvelope(() => apiClient.get("/banners/daily-deals/"));

    expect(data).toMatchObject({
      count: 2,
      next: null,
      previous: null,
      server_now: "2026-10-09T10:00:00+03:30",
      results: [{ id: 1 }, { id: 2 }],
    });
  });
});
