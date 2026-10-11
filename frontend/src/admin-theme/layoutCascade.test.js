/**
 * Layout regressions for the admin changelists (follow-up 2), resolved through
 * the REAL theme.css cascade (see test/adminCascade.js). jsdom does no layout,
 * so these tests check the declarations a browser would use, not pixels. The
 * pixel checks (overlap, overflow, widths) are in e2e/admin-layout.spec.js.
 */
import { afterEach, describe, expect, it } from "vitest";
import { mountAdminPage } from "../test/adminFrame";
import { readThemeCss, resolveStyle } from "../test/adminCascade";

const THEME = readThemeCss();

let mounted = null;
afterEach(() => {
  if (mounted) mounted.cleanup();
  mounted = null;
});

const CHANGELIST_HTML = `
<div id="content">
  <ul class="object-tools"><li><a class="addlink" href="#">اضافه‌کردن محصول</a></li></ul>
  <div id="changelist">
    <div id="toolbar"><input type="search"></div>
    <div class="results"><table id="result_list"><thead><tr><th>نام</th></tr></thead></table></div>
    <div class="actions"><select></select></div>
  </div>
</div>`;

function mountChangelist(width) {
  mounted = mountAdminPage(CHANGELIST_HTML, [], { css: THEME });
  const doc = mounted.doc;
  return {
    doc,
    style: (selector, prop) => resolveStyle(doc.querySelector(selector), prop, { width }),
  };
}

describe("item 3: object tools sit in their own row above the search card", () => {
  for (const width of [1280, 375]) {
    it(`is not floated over #toolbar at ${width}px`, () => {
      const { style } = mountChangelist(width);
      expect(style(".object-tools", "float")).toBe("none");
      expect(style(".object-tools li", "float")).toBe("none");
      expect(style(".object-tools a.addlink", "float")).toBe("none");
    });
  }

  it("has no negative top margin pulling it up onto the search card", () => {
    const { style } = mountChangelist(1280);
    expect(style(".object-tools", "margin-top")).not.toMatch(/^-/);
  });
});
describe("item 4: the changelist does not push the page sideways", () => {
  it("sizes the actions bar inside its card (border-box), so it does not overhang", () => {
    const desktop = mountChangelist(1280);
    expect(desktop.style("#changelist .actions", "box-sizing")).toBe("border-box");
    mounted.cleanup();
    const phone = mountChangelist(375);
    expect(phone.style("#changelist .actions", "box-sizing")).toBe("border-box");
  });

  it("lets a wide results table scroll inside its own wrapper on desktop", () => {
    const { style } = mountChangelist(1280);
    expect(style("#changelist .results", "overflow-x")).toBe("auto");
  });

  it("keeps the card layout on phones instead of a scrolling table", () => {
    const { style } = mountChangelist(375);
    expect(style("#changelist .results", "overflow-x")).toBe("visible");
  });
});

/*
 * Follow-up 3 (items 1, 2, 3, 6). The stock rules that each defect came from
 * are reproduced here, as they appear in Django's base.css and forms.css, and
 * placed before theme.css, the order base.html uses. The resolver then has to
 * pick the theme declaration over them, as a browser does.
 */
const STOCK_RULES = `
a:link, a:visited { color: #447e9b; text-decoration: none; }
.submit-row a.deletelink { background: var(--delete-button-bg); color: var(--button-fg); }
a.deletelink:link, a.deletelink:visited { color: #CC3434; }
a.deletelink:focus, a.deletelink:hover { color: #993333; }
`;

function mountWith(bodyHtml, width) {
  mounted = mountAdminPage(bodyHtml, [], { css: STOCK_RULES + THEME });
  const doc = mounted.doc;
  return { doc, style: (selector, prop) => resolveStyle(doc.querySelector(selector), prop, { width }) };
}

describe("item 1: the changelist header is a normal first row (no sticky offset)", () => {
  for (const width of [1024, 1280, 1440]) {
    it(`is not sticky at ${width}px`, () => {
      const { style } = mountWith(CHANGELIST_HTML, width);
      expect(style("#result_list thead th", "position")).toBe("static");
    });
  }
});

describe("item 2: the delete link keeps the danger text colour", () => {
  it("is the danger text token, not the stock white or #CC3434", () => {
    const { style } = mountWith(
      `<div class="submit-row"><a class="deletelink" href="#">حذف</a></div>`,
      1280,
    );
    expect(style(".submit-row a.deletelink", "color")).toBe("var(--cg-danger-text)");
  });
});

describe("item 3: the print button text stays gold on an <a>", () => {
  it("is gold on a link, not the stock link colour", () => {
    const { style } = mountWith(
      `<a class="cusin-btn cusin-btn--dark" href="#">چاپ</a>`,
      1280,
    );
    expect(style("a.cusin-btn--dark", "color")).toBe("var(--cg-gold)");
  });
});

describe("item 6: KPI tiles fit a 9-digit amount on one line", () => {
  const KPI_HTML = `
<section class="cusin-kpis"><article class="cusin-card cusin-kpi-card">
  <div class="cusin-kpi-grid"><div class="cusin-kpi"><span class="cusin-kpi-label">فروش</span>
  <strong class="cusin-kpi-value">۱۲۳٬۴۵۶٬۷۸۹ تومان</strong></div></div>
</article></section>`;

  it("uses auto-fit tiles of at least 180px on desktop", () => {
    const { style } = mountWith(KPI_HTML, 1280);
    expect(style(".cusin-kpi-grid", "grid-template-columns")).toBe(
      "repeat(auto-fit, minmax(min(180px, 100%), 1fr))",
    );
  });

  it("does not clip or ellipsise the value", () => {
    const { style } = mountWith(KPI_HTML, 1280);
    expect(style(".cusin-kpi-value", "text-overflow")).not.toBe("ellipsis");
    expect(style(".cusin-kpi-value", "overflow")).not.toBe("hidden");
  });
});
