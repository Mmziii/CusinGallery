/**
 * «گزارش‌ها و تحلیل» on phones (follow-up: the page scrolled ~46px sideways
 * at 390px and the range chips ran off the edge).
 *
 * Same approach as layoutCascade.test.js: resolve the declarations the real
 * stylesheets give an element at a viewport width, in the same order the
 * admin loads them (theme.css, then reports.css). jsdom does no layout, so
 * this pins the rules that keep the page inside the viewport rather than
 * measuring pixels; a browser check belongs in e2e/admin-layout.spec.js.
 */
import path from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, describe, expect, it } from "vitest";
import { readThemeCss, resolveStyle } from "../test/adminCascade";
import { mountAdminPage } from "../test/adminFrame";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const THEME_CSS = readThemeCss();
const REPORTS_CSS = readThemeCss(
  path.resolve(HERE, "../../../backend/static/admin_theme/css/reports.css")
);

/* Mirrors apps/analytics/templates/analytics/reports.html: the range card
   (six chips + the custom-date form), the section grid and a wide table. */
const REPORT_HTML = `
<div class="cusin-reports">
  <div id="content">
    <div class="cusin-report">
      <section class="cusin-card cusin-report-head">
        <div class="cusin-report-range">
          <p class="cusin-report-range-line">بازهٔ گزارش: <strong>۱۴۰۵/۰۷/۱۸ تا ۱۴۰۵/۰۷/۱۸</strong></p>
          <div class="cusin-days-toggle" role="group">
            <a class="cusin-chip is-active" href="#">امروز</a>
            <a class="cusin-chip" href="#">۷ روز</a>
            <a class="cusin-chip" href="#">۳۰ روز</a>
            <a class="cusin-chip" href="#">۹۰ روز</a>
            <a class="cusin-chip" href="#">امسال</a>
            <a class="cusin-chip" href="#">بازهٔ دلخواه</a>
          </div>
        </div>
        <div class="cusin-report-tools">
          <a class="cusin-report-print" href="#">نسخهٔ چاپی / PDF</a>
        </div>
        <form class="cusin-report-custom">
          <label>از <input type="text" value="۱۴۰۵/۰۷/۰۱"></label>
          <label>تا <input type="text" value="۱۴۰۵/۰۷/۱۸"></label>
          <button class="cusin-report-apply" type="submit">نمایش بازهٔ دلخواه</button>
        </form>
      </section>
      <div class="cusin-report-grid">
        <section class="cusin-card">
          <div class="cusin-table-scroll">
            <table class="cusin-mini-table cusin-report-table">
              <thead><tr><th scope="col">محصول</th><th scope="col">تعداد</th></tr></thead>
              <tbody><tr><td>سایز ۲۸ کد ۹۹۱۵</td><td class="cusin-nowrap">۲</td></tr></tbody>
            </table>
          </div>
        </section>
      </div>
      <div class="cusin-report-charts">
        <section class="cusin-card"><ol class="cusin-funnel"><li class="cusin-funnel-step">
          <span class="cusin-funnel-label">بازدید محصول</span>
          <span class="cusin-funnel-bar"><i style="width: 100%"></i></span>
          <span class="cusin-funnel-count">۱۲ نشست</span>
          <span class="cusin-funnel-drop">افت: ۰٪</span>
        </li></ol></section>
      </div>
    </div>
  </div>
</div>`;

let mounted = null;
afterEach(() => {
  if (mounted) mounted.cleanup();
  mounted = null;
});

function mountReport(width) {
  mounted = mountAdminPage(REPORT_HTML, [], {
    css: `${THEME_CSS}\n${REPORTS_CSS}`,
  });
  const doc = mounted.doc;
  return {
    doc,
    style: (selector, prop) => resolveStyle(doc.querySelector(selector), prop, { width }),
  };
}

// The reported defect was at 390px; 768px is the top of the phone/tablet
// range the same rules must cover (the file switches at 900px).
for (const width of [390, 768]) {
  describe(`reports page fits the viewport at ${width}px`, () => {
    it("keeps the page and its cards at 100% width, never wider", () => {
      const { style } = mountReport(width);
      for (const selector of [
        ".cusin-reports #content",
        ".cusin-reports .cusin-report",
        ".cusin-report-head",
        ".cusin-card",
      ]) {
        expect(style(selector, "max-width")).toBe("100%");
        expect(style(selector, "min-width")).toBe("0");
      }
    });

    it("stacks the header (range, chips, tools, custom form) in one column", () => {
      const { style } = mountReport(width);
      expect(style(".cusin-report-head", "flex-direction")).toBe("column");
      expect(style(".cusin-report-range", "width")).toBe("100%");
      expect(style(".cusin-report-tools", "width")).toBe("100%");
      expect(style(".cusin-report-print", "width")).toBe("100%");
    });

    it("wraps the preset chips inside their own row", () => {
      const { style } = mountReport(width);
      expect(style(".cusin-days-toggle", "flex-wrap")).toBe("wrap");
      expect(style(".cusin-days-toggle", "width")).toBe("100%");
      expect(style(".cusin-days-toggle", "display")).toBe("flex");
      expect(style(".cusin-chip", "flex")).toMatch(/^1 1/);
    });

    it("lets the date inputs and the apply button fit the card", () => {
      const { style } = mountReport(width);
      expect(style('.cusin-report-custom input[type="text"]', "width")).toBe("100%");
      expect(style('.cusin-report-custom input[type="text"]', "box-sizing")).toBe("border-box");
      expect(style(".cusin-report-apply", "width")).toBe("100%");
    });

    it("stacks the section cards in a single column", () => {
      const { style } = mountReport(width);
      expect(style(".cusin-report-grid", "grid-template-columns")).toBe("minmax(0, 1fr)");
      expect(style(".cusin-report-charts", "grid-template-columns")).toBe("minmax(0, 1fr)");
    });

    it("scrolls wide tables inside their wrapper, not the page", () => {
      const { style } = mountReport(width);
      expect(style(".cusin-table-scroll", "overflow-x")).toBe("auto");
      expect(style(".cusin-table-scroll", "max-width")).toBe("100%");
      expect(style(".cusin-table-scroll", "min-width")).toBe("0");
      // The table itself stays wide -- the wrapper is its scrollport.
      expect(style(".cusin-report-table", "min-width")).toBe("46rem");
    });
  });
}

describe("reports page keeps its desktop layout above 900px", () => {
  it("keeps the range card on one row with inline chips", () => {
    const { style } = mountReport(1280);
    expect(style(".cusin-report-head", "flex-direction")).not.toBe("column");
    expect(style(".cusin-days-toggle", "display")).toBe("inline-flex");
    expect(style(".cusin-days-toggle", "width")).not.toBe("100%");
  });

  it("keeps the fixed-width date inputs and the auto-fit card grid", () => {
    const { style } = mountReport(1280);
    expect(style('.cusin-report-custom input[type="text"]', "width")).toBe("10.5rem");
    expect(style(".cusin-report-grid", "grid-template-columns")).toMatch(/auto-fit/);
  });
});
