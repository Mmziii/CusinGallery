/**
 * B6 + B3c: the admin quick-search palette (Ctrl+K, "/", arrows, Enter,
 * Escape, debounce, grouped results, throttling) and the order quick-status
 * guard, executed for real from backend/static/admin_theme/js/theme.js.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { waitFor } from "@testing-library/dom";
import { jsonResponse, mountAdminPage, readAdminScript } from "../test/adminFrame";

const SEARCH_URL = "/admin/quick-search/";

const PALETTE_HTML = `
<button type="button" data-cusin-search-open data-search-url="${SEARCH_URL}">جستجو</button>
<div data-cusin-palette hidden>
  <div data-cusin-palette-backdrop></div>
  <div role="dialog">
    <input type="search" data-cusin-palette-input aria-label="عبارت جستجو">
    <button type="button" data-cusin-palette-close>بستن</button>
    <div data-cusin-palette-results role="listbox"></div>
  </div>
</div>
<input id="outside-field" type="text">
`;

const SEARCH_RESULTS = {
  query: "کتری",
  groups: [
    {
      id: "orders",
      label: "سفارش‌ها",
      results: [
        { title: "ORD-1001", subtitle: "پرداخت شده", url: "/admin/orders/order/1/change/" },
      ],
    },
    {
      id: "products",
      label: "محصولات",
      results: [
        { title: "کتری لعابی", subtitle: "KT-1", url: "/admin/products/product/2/change/" },
        { title: "کتری استیل", subtitle: "KT-2", url: "/admin/products/product/3/change/" },
      ],
    },
  ],
};

const FRAGMENT_RESULTS = {
  groups: [{
    id: "products",
    label: "محصولات",
    results: [
      { title: "کتری لعابی", subtitle: "KT-1", url: "#product-2" },
      { title: "کتری استیل", subtitle: "KT-2", url: "#product-3" },
    ],
  }],
};

let mounted = null;
afterEach(() => {
  if (mounted) mounted.cleanup();
  mounted = null;
});

function mountPalette(fetchImpl) {
  mounted = mountAdminPage(PALETTE_HTML, [readAdminScript("theme.js")], {
    fetch: fetchImpl,
  });
  const { doc, win } = mounted;
  const root = doc.querySelector("[data-cusin-palette]");
  const input = doc.querySelector("[data-cusin-palette-input]");
  const results = doc.querySelector("[data-cusin-palette-results]");
  const opener = doc.querySelector("[data-cusin-search-open]");
  const key = (target, init) => {
    const event = new win.KeyboardEvent("keydown", { bubbles: true, cancelable: true, ...init });
    target.dispatchEvent(event);
    return event;
  };
  const type = (value) => {
    input.value = value;
    input.dispatchEvent(new win.Event("input", { bubbles: true }));
  };
  const rows = () => [...results.querySelectorAll(".cusin-prow")];
  return { doc, win, root, input, results, opener, key, type, rows };
}

describe("palette: opening and closing", () => {
  it("opens with Ctrl+K, focuses the input, and closes on a second Ctrl+K", () => {
    const p = mountPalette(() => jsonResponse({ groups: [] }));
    expect(p.root.hidden).toBe(true);
    p.key(p.doc.body, { key: "k", ctrlKey: true });
    expect(p.root.hidden).toBe(false);
    expect(p.doc.activeElement).toBe(p.input);
    p.key(p.input, { key: "k", ctrlKey: true });
    expect(p.root.hidden).toBe(true);
  });

  it("opens with Cmd+K on macOS", () => {
    const p = mountPalette(() => jsonResponse({ groups: [] }));
    p.key(p.doc.body, { key: "K", metaKey: true });
    expect(p.root.hidden).toBe(false);
  });

  it("opens with '/' when no field is focused", () => {
    const p = mountPalette(() => jsonResponse({ groups: [] }));
    const event = p.key(p.doc.body, { key: "/" });
    expect(p.root.hidden).toBe(false);
    expect(event.defaultPrevented).toBe(true);
  });

  it("does not open with '/' while typing in another field", () => {
    const p = mountPalette(() => jsonResponse({ groups: [] }));
    const field = p.doc.getElementById("outside-field");
    p.key(field, { key: "/" });
    expect(p.root.hidden).toBe(true);
  });

  it("closes with Escape and returns focus to the opener", () => {
    const p = mountPalette(() => jsonResponse({ groups: [] }));
    p.opener.click();
    expect(p.root.hidden).toBe(false);
    p.key(p.input, { key: "Escape" });
    expect(p.root.hidden).toBe(true);
    expect(p.doc.activeElement).toBe(p.opener);
  });

  it("closes from the backdrop/close control", () => {
    const p = mountPalette(() => jsonResponse({ groups: [] }));
    p.opener.click();
    p.doc.querySelector("[data-cusin-palette-close]").click();
    expect(p.root.hidden).toBe(true);
  });
});

describe("palette: searching", () => {
  it("does not query the server for a single character", async () => {
    const fetchSpy = vi.fn(() => jsonResponse(SEARCH_RESULTS));
    const p = mountPalette(fetchSpy);
    p.opener.click();
    p.type("ک");
    await new Promise((resolve) => setTimeout(resolve, 300));
    expect(fetchSpy).not.toHaveBeenCalled();
    expect(p.results.textContent).toContain("دست‌کم ۲ حرف");
  });

  it("debounces: a burst of keystrokes causes one request with the encoded query", async () => {
    const fetchSpy = vi.fn(() => jsonResponse(SEARCH_RESULTS));
    const p = mountPalette(fetchSpy);
    p.opener.click();
    p.type("ک");
    p.type("کت");
    p.type("کتر");
    p.type("کتری");
    await waitFor(() => expect(fetchSpy).toHaveBeenCalledTimes(1), { timeout: 1000 });
    expect(fetchSpy.mock.calls[0][0]).toBe(`${SEARCH_URL}?q=${encodeURIComponent("کتری")}`);
    expect(fetchSpy.mock.calls[0][1].credentials).toBe("same-origin");
  });

  it("renders groups in order with their labels, titles, subtitles and links", async () => {
    const p = mountPalette(() => jsonResponse(SEARCH_RESULTS));
    p.opener.click();
    p.type("کتری");
    await waitFor(() => expect(p.rows().length).toBe(3));
    const labels = [...p.results.querySelectorAll(".cusin-pgroup-label")].map((el) => el.textContent);
    expect(labels).toEqual(["سفارش‌ها", "محصولات"]);
    const first = p.rows()[0];
    expect(first.getAttribute("href")).toBe("/admin/orders/order/1/change/");
    expect(first.querySelector(".cusin-prow-title").textContent).toBe("ORD-1001");
    expect(first.querySelector(".cusin-prow-sub").textContent).toBe("پرداخت شده");
    // icons come from the one sprite, by name
    expect(first.querySelector("use").getAttribute("href")).toBe("#cusin-i-receipt");
  });

  it("escapes result text so markup in data cannot inject HTML", async () => {
    const hostile = {
      groups: [{
        id: "products",
        label: "محصولات",
        results: [{ title: "<img src=x onerror=alert(1)>", subtitle: "", url: "/x/" }],
      }],
    };
    const p = mountPalette(() => jsonResponse(hostile));
    p.opener.click();
    p.type("کتری");
    await waitFor(() => expect(p.rows().length).toBe(1));
    expect(p.results.querySelector("img")).toBeNull();
    expect(p.rows()[0].querySelector(".cusin-prow-title").textContent).toBe(
      "<img src=x onerror=alert(1)>"
    );
  });

  it("says so when nothing matches", async () => {
    const p = mountPalette(() => jsonResponse({ query: "x", groups: [] }));
    p.opener.click();
    p.type("zzz");
    await waitFor(() => expect(p.results.textContent).toContain("نتیجه‌ای پیدا نشد."));
  });

  it("shows the throttling message on HTTP 429", async () => {
    const p = mountPalette(() => jsonResponse({ detail: "slow down" }, 429));
    p.opener.click();
    p.type("کتری");
    await waitFor(() => expect(p.results.textContent).toContain("تعداد درخواست‌ها زیاد است"));
  });

  it("reports a failed request instead of showing stale results", async () => {
    const p = mountPalette(() => jsonResponse({}, 500));
    p.opener.click();
    p.type("کتری");
    await waitFor(() => expect(p.results.textContent).toContain("جستجو در دسترس نیست"));
    expect(p.rows().length).toBe(0);
  });
});

describe("palette: keyboard navigation", () => {
  async function withResults() {
    const p = mountPalette(() => jsonResponse(SEARCH_RESULTS));
    p.opener.click();
    p.type("کتری");
    await waitFor(() => expect(p.rows().length).toBe(3));
    return p;
  }
  const activeIndex = (p) => p.rows().findIndex((row) => row.classList.contains("is-active"));

  it("moves down with ArrowDown and wraps from the last row to the first", async () => {
    const p = await withResults();
    p.key(p.input, { key: "ArrowDown" });
    expect(activeIndex(p)).toBe(0);
    p.key(p.input, { key: "ArrowDown" });
    expect(activeIndex(p)).toBe(1);
    p.key(p.input, { key: "ArrowDown" });
    p.key(p.input, { key: "ArrowDown" });
    expect(activeIndex(p)).toBe(0);
  });

  it("moves up with ArrowUp and wraps from the first row to the last", async () => {
    const p = await withResults();
    p.key(p.input, { key: "ArrowDown" });
    p.key(p.input, { key: "ArrowUp" });
    expect(activeIndex(p)).toBe(2);
  });

  it("keeps aria-selected in sync with the active row", async () => {
    const p = await withResults();
    p.key(p.input, { key: "ArrowDown" });
    p.key(p.input, { key: "ArrowDown" });
    const selected = p.rows().map((row) => row.getAttribute("aria-selected"));
    expect(selected).toEqual(["false", "true", "false"]);
  });

  it("Enter with an active row navigates to that row's link", async () => {
    // jsdom cannot load other pages, but it does implement fragment (hash)
    // navigation, so the rows here link to fragments and we assert the
    // iframe's location really changed to the active row's target.
    const p = mountPalette(() => jsonResponse(FRAGMENT_RESULTS));
    p.opener.click();
    p.type("کتری");
    await waitFor(() => expect(p.rows().length).toBe(2));
    p.key(p.input, { key: "ArrowDown" });
    p.key(p.input, { key: "ArrowDown" });
    const event = p.key(p.input, { key: "Enter" });
    expect(event.defaultPrevented).toBe(true);
    await waitFor(() => expect(p.win.location.hash).toBe("#product-3"));
  });

  it("Enter with no active row does nothing and keeps the palette open", async () => {
    const p = await withResults();
    const event = p.key(p.input, { key: "Enter" });
    expect(event.defaultPrevented).toBe(true);
    expect(p.root.hidden).toBe(false);
  });

  it("Escape from the results closes the palette", async () => {
    const p = await withResults();
    p.key(p.input, { key: "Escape" });
    expect(p.root.hidden).toBe(true);
  });
});

describe("order quick-status guard (B3c)", () => {
  const QUICK_HTML = `
<form class="cusin-quick-form" method="post" action="/admin/orders/order/9/quick-status/">
  <div class="cusin-quick-field">
    <input type="text" id="cusin-quick-tracking" name="tracking_code" maxlength="100">
  </div>
  <div class="cusin-quick-actions">
    <button type="submit" name="next_status" value="shipped" class="cusin-btn">ارسال شده</button>
    <button type="submit" name="next_status" value="cancelled" class="cusin-btn cusin-btn--danger">لغو</button>
  </div>
</form>`;

  function mountQuick() {
    mounted = mountAdminPage(QUICK_HTML, [readAdminScript("theme.js")]);
    const { doc, win } = mounted;
    const form = doc.querySelector("form.cusin-quick-form");
    const tracking = doc.getElementById("cusin-quick-tracking");
    const submits = [];
    form.addEventListener("submit", (event) => {
      event.preventDefault(); // jsdom cannot submit
      submits.push(event);
    });
    return { doc, win, form, tracking, submits, button: (v) => form.querySelector(`button[value="${v}"]`) };
  }

  it("blocks «ارسال شده» without a tracking code and focuses the field", () => {
    const q = mountQuick();
    q.button("shipped").click();
    expect(q.submits.length).toBe(0);
    expect(q.doc.activeElement).toBe(q.tracking);
    expect(q.tracking.getAttribute("aria-invalid")).toBe("true");
  });

  it("treats a whitespace-only tracking code as empty", () => {
    const q = mountQuick();
    q.tracking.value = "   ";
    q.button("shipped").click();
    expect(q.submits.length).toBe(0);
  });

  it("lets «ارسال شده» through once a tracking code is entered", () => {
    const q = mountQuick();
    q.tracking.value = "1234567890";
    q.button("shipped").click();
    expect(q.submits.length).toBe(1);
  });

  it("clears the invalid marker when the owner starts typing", () => {
    const q = mountQuick();
    q.button("shipped").click();
    q.tracking.value = "1";
    q.tracking.dispatchEvent(new q.win.Event("input", { bubbles: true }));
    expect(q.tracking.hasAttribute("aria-invalid")).toBe(false);
  });

  it("never blocks other transitions (the server still validates them)", () => {
    const q = mountQuick();
    q.button("cancelled").click();
    expect(q.submits.length).toBe(1);
  });
});
