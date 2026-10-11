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
