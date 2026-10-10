/**
 * Regression tests for "closed components are really closed".
 *
 * The defect: `.cusin-palette { display: flex }` overrode the browser's own
 * [hidden] { display: none }, so the palette was visible on every page and
 * never closed. The tests load the REAL theme.css text into the page under
 * test, run the REAL scripts, and resolve the display/visibility a browser
 * would use (see test/cssCascade.js). They assert what is on screen, not only
 * that the hidden attribute was toggled.
 */
import { afterEach, describe, expect, it } from "vitest";
import { waitFor } from "@testing-library/dom";
import { jsonResponse, mountAdminPage, readAdminScript } from "../test/adminFrame";
import { readThemeCss, resolveStyle } from "../test/adminCascade";

const THEME = readThemeCss();
const DESKTOP = 1280;
const PHONE = 800;

const SHELL_HTML = `
<button type="button" id="cusin-drawer-toggle" class="cusin-drawer-toggle" aria-controls="cusin-drawer" aria-expanded="false">منو</button>
<button type="button" class="cusin-search-trigger" data-cusin-search-open data-search-url="/admin/quick-search/">جستجو در پنل…</button>
<div class="cusin-drawer-scrim" data-cusin-drawer-scrim hidden></div>
<nav class="cusin-drawer" id="cusin-drawer" aria-label="ناوبری پنل">
  <a class="cusin-drawer-dash" id="drawer-link" href="/admin/">پیشخوان</a>
</nav>
<div class="cusin-palette" data-cusin-palette hidden>
  <div class="cusin-palette-backdrop" data-cusin-palette-close></div>
  <div class="cusin-palette-box" role="dialog" aria-modal="true" aria-label="جستجوی سریع در پنل">
    <div class="cusin-palette-input-row">
      <input type="search" data-cusin-palette-input aria-label="عبارت جستجو">
    </div>
    <div class="cusin-palette-results" data-cusin-palette-results role="listbox"></div>
  </div>
</div>`;

const FRAGMENT_RESULTS = {
  groups: [{
    id: "products",
    label: "محصولات",
    results: [{ title: "کتری", subtitle: "KT-1", url: "#product-2" }],
  }],
};

const PRODUCT_HTML = `
<div id="content-main">
<form method="post" action="">
  <input type="text" id="id_name" name="name" value="">
  <input type="number" id="id_price" name="price" value="1234567">
  <input type="number" id="id_compare_at_price" name="compare_at_price" value="">
  <div class="submit-row"><input type="submit" name="_save" class="default" value="ذخیره"></div>
</form>
</div>
<div data-cusin-preview>
  <span data-cusin-preview-name>نام محصول</span>
  <span data-cusin-preview-price>—</span>
  <span class="cusin-preview-old" data-cusin-preview-compare hidden></span>
  <div data-cusin-preview-image></div>
</div>`;

let mounted = null;
afterEach(() => {
  if (mounted) mounted.cleanup();
  mounted = null;
});

function mountShell({ width = DESKTOP, css = THEME, fetch } = {}) {
  mounted = mountAdminPage(SHELL_HTML, [readAdminScript("theme.js")], { css, fetch });
  const { doc, win } = mounted;
  const el = (selector) => doc.querySelector(selector);
  const shown = (node, prop = "display") => resolveStyle(node, prop, { width });
  const key = (target, init) => {
    target.dispatchEvent(new win.KeyboardEvent("keydown", { bubbles: true, cancelable: true, ...init }));
  };
  return { doc, win, el, shown, key };
}

describe("the cascade resolver follows the CSS rules (checked against the spec)", () => {
  // Each case: a stylesheet, and what a browser shows for a [hidden] element and a shown one.
  const cases = [
    {
      name: "!important [hidden] wins even when the author rule comes later",
      css: "[hidden]{display:none !important} .pal{display:flex}",
      hidden: "none",
      shown: "flex",
    },
    {
      name: "!important [hidden] wins when it comes first (source order is not the rule)",
      css: ".pal{display:flex} [hidden]{display:none !important}",
      hidden: "none",
      shown: "flex",
    },
    {
      name: "a higher-specificity author rule beats [hidden] without !important",
      css: "[hidden]{display:none} #root .pal{display:flex}",
      hidden: "flex",
      shown: "flex",
    },
    {
      name: "with no [hidden] rule the author display wins (the defect)",
      css: ".pal{display:flex}",
      hidden: "flex",
      shown: "flex",
    },
  ];
  for (const testCase of cases) {
    it(testCase.name, () => {
      mounted = mountAdminPage('<div id="root"><div class="pal" id="p" hidden></div></div>', [], {
        css: testCase.css,
      });
      const node = mounted.doc.getElementById("p");
      expect(resolveStyle(node, "display")).toBe(testCase.hidden);
      node.removeAttribute("hidden");
      expect(resolveStyle(node, "display")).toBe(testCase.shown);
    });
  }
});

describe("quick-search palette with the real theme.css", () => {
  it("is not visible after the page loads", () => {
    const { el, shown } = mountShell();
    expect(el("[data-cusin-palette]").hidden).toBe(true);
    expect(shown(el("[data-cusin-palette]"))).toBe("none");
  });

  it("is visible while open and gone again after Escape", () => {
    const { el, shown, key, doc } = mountShell();
    key(doc.body, { key: "k", ctrlKey: true });
    expect(shown(el("[data-cusin-palette]"))).not.toBe("none");
    key(el("[data-cusin-palette-input]"), { key: "Escape" });
    expect(shown(el("[data-cusin-palette]"))).toBe("none");
  });

  it("opens from the topbar button and closes on a backdrop click", () => {
    const { el, shown } = mountShell();
    el("[data-cusin-search-open]").click();
    expect(shown(el("[data-cusin-palette]"))).not.toBe("none");
    el(".cusin-palette-backdrop").click();
    expect(shown(el("[data-cusin-palette]"))).toBe("none");
  });

  it("opens with '/' and closes after a result is chosen", async () => {
    const { el, shown, key, doc, win } = mountShell({
      fetch: () => jsonResponse(FRAGMENT_RESULTS),
    });
    key(doc.body, { key: "/" });
    expect(shown(el("[data-cusin-palette]"))).not.toBe("none");
    const input = el("[data-cusin-palette-input]");
    input.value = "کتری";
    input.dispatchEvent(new win.Event("input", { bubbles: true }));
    await waitFor(() => expect(el(".cusin-prow")).not.toBeNull());
    el(".cusin-prow").click();
    expect(shown(el("[data-cusin-palette]"))).toBe("none");
  });

  it("stays closed when the page is restored from the back/forward cache", () => {
    const { el, shown, key, doc, win } = mountShell();
    key(doc.body, { key: "k", ctrlKey: true });
    expect(shown(el("[data-cusin-palette]"))).not.toBe("none");
    win.dispatchEvent(new win.Event("pagehide"));
    expect(shown(el("[data-cusin-palette]"))).toBe("none");
  });

  it("is closed by default at phone width too, and Ctrl+K opens it there", () => {
    const { el, shown, doc, key } = mountShell({ width: PHONE });
    expect(shown(el("[data-cusin-palette]"), "display")).toBe("none");
    key(doc.body, { key: "k", ctrlKey: true });
    expect(shown(el("[data-cusin-palette]"), "display")).not.toBe("none");
  });
});

describe("sidebar drawer and its scrim with the real theme.css", () => {
  it("the scrim is hidden on a phone until the drawer opens, then hidden again", () => {
    const { el, shown } = mountShell({ width: PHONE });
    expect(shown(el("[data-cusin-drawer-scrim]"))).toBe("none");
    el("#cusin-drawer-toggle").click();
    expect(shown(el("[data-cusin-drawer-scrim]"))).not.toBe("none");
    expect(el("#cusin-drawer-toggle").getAttribute("aria-expanded")).toBe("true");
    el("#cusin-drawer-toggle").click();
    expect(shown(el("[data-cusin-drawer-scrim]"))).toBe("none");
  });

  it("the scrim is never shown on desktop, where the drawer is a fixed sidebar", () => {
    const { el, shown } = mountShell({ width: DESKTOP });
    expect(shown(el("[data-cusin-drawer-scrim]"))).toBe("none");
  });

  it("a closed phone drawer is invisible, so its links are not focusable", () => {
    const { el, shown } = mountShell({ width: PHONE });
    const drawer = el("#cusin-drawer");
    const link = el("#drawer-link");
    expect(shown(drawer, "visibility")).toBe("hidden");
    // visibility is inherited: the link inside the closed drawer is hidden too
    expect(shown(link, "visibility")).toBe("hidden");
    el("#cusin-drawer-toggle").click();
    expect(shown(drawer, "visibility")).toBe("visible");
    expect(shown(link, "visibility")).toBe("visible");
  });

  it("the drawer is a normal sidebar on desktop and is never hidden there", () => {
    const { el, shown } = mountShell({ width: DESKTOP });
    expect(shown(el("#cusin-drawer"), "visibility")).toBe("visible");
  });
});

describe("compare-at price in the product form with the real theme.css", () => {
  it("is hidden when there is no compare-at price and shown when there is one", () => {
    mounted = mountAdminPage(PRODUCT_HTML, [readAdminScript("product_form.js")], { css: THEME });
    const { doc, win } = mounted;
    const compare = doc.querySelector("[data-cusin-preview-compare]");
    expect(resolveStyle(compare, "display", { width: DESKTOP })).toBe("none");
    const input = doc.getElementById("id_compare_at_price");
    input.value = "2000000";
    input.dispatchEvent(new win.Event("input", { bubbles: true }));
    expect(compare.hidden).toBe(false);
    expect(resolveStyle(compare, "display", { width: DESKTOP })).not.toBe("none");
    input.value = "";
    input.dispatchEvent(new win.Event("input", { bubbles: true }));
    expect(resolveStyle(compare, "display", { width: DESKTOP })).toBe("none");
  });
});
