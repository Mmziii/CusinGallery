/**
 * Task 2: the live theme preview inside «محتوا و ظاهر سایت».
 *
 * These tests run the REAL admin script (backend/static/admin_theme/js) and
 * assert the exact variables it paints: preset inheritance, per-field
 * overrides, radius/font/shadow choices, and the confirmed reset POST.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { mountAdminPage, readAdminScript } from "../test/adminFrame";

const PRESETS = {
  olive_gold: {
    label: "زیتونی و طلایی",
    primary: "#637037",
    accent: "#CEB464",
    background: "#FAF7F0",
    text: "#1E2412",
    header_background: "#FFFFFF",
    header_text: "#1E2412",
    button_text: "#FFFFFF",
  },
  cream_brown: {
    label: "کرم و قهوه‌ای",
    primary: "#7A4B2A",
    accent: "#C9A227",
    background: "#FBF6EC",
    text: "#33251A",
    header_background: "#FBF6EC",
    header_text: "#33251A",
    button_text: "#FFFFFF",
  },
};

function page({ preset = "olive_gold", primary = "" } = {}) {
  return `
  <form id="sitesettings_form">
    <input type="hidden" name="csrfmiddlewaretoken" value="csrf-token">
    <select name="theme_preset">
      <option value="olive_gold"${preset === "olive_gold" ? " selected" : ""}>زیتونی و طلایی</option>
      <option value="cream_brown"${preset === "cream_brown" ? " selected" : ""}>کرم و قهوه‌ای</option>
    </select>
    <input name="theme_primary" value="${primary}">
    <input name="theme_accent" value="">
    <input name="theme_background" value="">
    <input name="theme_text" value="">
    <input name="theme_header_background" value="">
    <input name="theme_header_text" value="">
    <input name="theme_button_text" value="">
    <select name="theme_button_radius">
      <option value="medium" selected>متوسط</option>
      <option value="none">بدون گردی</option>
      <option value="large">زیاد</option>
    </select>
    <select name="theme_base_font_size">
      <option value="normal" selected>معمولی</option>
      <option value="large">بزرگ</option>
    </select>
    <select name="theme_card_shadow">
      <option value="soft" selected>ملایم</option>
      <option value="none">بدون سایه</option>
    </select>
  </form>
  <div id="cusin-theme-preview">
    <div id="cusin-theme-preview-frame">
      <div class="cusin-tp-header"><span class="cusin-tp-logo">کازین گالری</span></div>
      <button type="button" class="cusin-tp-btn">افزودن به سبد خرید</button>
    </div>
    <button type="button" id="cusin-theme-reset"
            data-reset-url="/admin/core/sitesettings/reset-theme/"
            data-confirm="بازگشت به پیش‌فرض؟">بازگشت به تنظیمات پیش‌فرض</button>
  </div>
  <script type="application/json" id="cusin-theme-presets">${JSON.stringify(PRESETS)}</script>`;
}

let mounted;
afterEach(() => {
  if (mounted) mounted.cleanup();
  mounted = null;
  vi.restoreAllMocks();
});

async function mount(options) {
  mounted = mountAdminPage(page(options), [readAdminScript("theme_preview.js")]);
  await new Promise((resolve) => setTimeout(resolve, 20));
  return mounted;
}

function variable(doc, name) {
  const frame = doc.getElementById("cusin-theme-preview-frame");
  return frame.style.getPropertyValue(name);
}

describe("theme live preview (Task 2)", () => {
  it("paints the selected preset on load", async () => {
    const { doc } = await mount();
    expect(variable(doc, "--cusin-tp-primary")).toBe("#637037");
    expect(variable(doc, "--cusin-tp-accent")).toBe("#CEB464");
    expect(variable(doc, "--cusin-tp-bg")).toBe("#FAF7F0");
    expect(variable(doc, "--cusin-tp-header-bg")).toBe("#FFFFFF");
    expect(variable(doc, "--cusin-tp-radius")).toBe("12px");
    expect(variable(doc, "--cusin-tp-font-size")).toBe("1rem");
    expect(variable(doc, "--cusin-tp-shadow")).not.toBe("none");
  });

  it("updates live when a custom color is typed", async () => {
    const { doc } = await mount();
    const input = doc.querySelector('[name="theme_primary"]');
    input.value = "#123456";
    doc.getElementById("sitesettings_form").dispatchEvent(new Event("input", { bubbles: true }));
    expect(variable(doc, "--cusin-tp-primary")).toBe("#123456");
  });

  it("switching the preset replaces inherited colors and placeholders", async () => {
    const { doc } = await mount();
    const select = doc.querySelector('[name="theme_preset"]');
    select.value = "cream_brown";
    select.dispatchEvent(new Event("change", { bubbles: true }));
    expect(variable(doc, "--cusin-tp-primary")).toBe("#7A4B2A");
    expect(variable(doc, "--cusin-tp-bg")).toBe("#FBF6EC");
    expect(doc.querySelector('[name="theme_primary"]').getAttribute("placeholder")).toBe("#7A4B2A");
  });

  it("applies radius, font size and shadow choices", async () => {
    const { doc } = await mount();
    const radius = doc.querySelector('[name="theme_button_radius"]');
    const font = doc.querySelector('[name="theme_base_font_size"]');
    const shadow = doc.querySelector('[name="theme_card_shadow"]');
    radius.value = "none";
    font.value = "large";
    shadow.value = "none";
    doc.getElementById("sitesettings_form").dispatchEvent(new Event("change", { bubbles: true }));
    expect(variable(doc, "--cusin-tp-radius")).toBe("0");
    expect(variable(doc, "--cusin-tp-font-size")).toBe("1.125rem");
    expect(variable(doc, "--cusin-tp-shadow")).toBe("none");
  });

  it("reset asks for confirmation and posts with CSRF", async () => {
    const { doc, win } = await mount();
    win.confirm = vi.fn(() => true);
    const submit = vi.fn();
    win.HTMLFormElement.prototype.submit = submit;

    doc.getElementById("cusin-theme-reset").click();

    expect(win.confirm).toHaveBeenCalled();
    expect(submit).toHaveBeenCalledTimes(1);
    const forms = [...doc.body.querySelectorAll("form")];
    const resetForm = forms[forms.length - 1];
    expect(resetForm.method).toBe("post");
    expect(resetForm.getAttribute("action")).toBe("/admin/core/sitesettings/reset-theme/");
    expect(resetForm.querySelector('input[name="csrfmiddlewaretoken"]').value).toBe("csrf-token");
  });

  it("does not post when the owner cancels the confirmation", async () => {
    const { doc, win } = await mount();
    win.confirm = vi.fn(() => false);
    const submit = vi.fn();
    win.HTMLFormElement.prototype.submit = submit;

    doc.getElementById("cusin-theme-reset").click();
    expect(submit).not.toHaveBeenCalled();
  });
});
