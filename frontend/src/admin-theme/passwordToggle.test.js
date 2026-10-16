/**
 * Audit 19 item 3 (admin side): the eye button on every password field of
 * the light admin panel.
 *
 * The login page ships the control as markup
 * (backend/templates/admin/login.html); everything else -- the
 * password-change form, the reset-confirm form, the user change form -- gets
 * it from the REAL `initPasswordToggles()` in
 * backend/static/admin_theme/js/theme.js, which these tests execute inside an
 * isolated jsdom frame (see ../test/adminFrame).
 *
 * Contract, identical to the storefront's PasswordInput:
 *   tap = type="text", tap again = type="password";
 *   eye / eye-off, aria-label «نمایش رمز» / «پنهان کردن رمز», aria-pressed;
 *   a 40px tap target placed at the inline end (the LEFT side in RTL);
 *   `type="button"`, so it can never submit the form.
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { afterEach, describe, expect, it, vi } from "vitest";

import { mountAdminPage, readAdminScript } from "../test/adminFrame";

const SPRITE_PATH = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../../../backend/apps/adminui/templates/adminui/_sprite.html"
);

const THEME_JS = readAdminScript("theme.js");

const PLAIN_FORM = `
<form id="change-password" method="post">
  <div class="form-row">
    <label for="id_old_password">رمز عبور فعلی:</label>
    <input type="password" name="old_password" id="id_old_password" autocomplete="current-password">
  </div>
  <div class="form-row">
    <label for="id_new_password1">رمز عبور جدید:</label>
    <input type="password" name="new_password1" id="id_new_password1" autocomplete="new-password">
  </div>
  <input type="text" name="unrelated" id="id_unrelated">
  <input type="submit" value="تغییر گذرواژه">
</form>
`;

/** What backend/templates/admin/login.html renders (server-side markup). */
const LOGIN_FORM = `
<form action="/admin/" method="post" id="login-form">
  <div class="form-row cusin-password-row">
    <label for="id_password">گذرواژه:</label>
    <span class="cusin-password">
      <input type="password" name="password" id="id_password" autocomplete="current-password">
      <button type="button" class="cusin-password-toggle" data-cusin-password-toggle
              aria-label="نمایش رمز" aria-pressed="false" title="نمایش رمز"
              aria-controls="id_password">
        <svg class="cusin-icon cusin-icon--eye" aria-hidden="true"><use href="#cusin-i-eye"></use></svg>
        <svg class="cusin-icon cusin-icon--eye-off" aria-hidden="true"><use href="#cusin-i-eye-off"></use></svg>
      </button>
    </span>
  </div>
  <div class="submit-row"><input type="submit" value="ورود"></div>
</form>
`;

let mounted = null;
afterEach(() => {
  if (mounted) mounted.cleanup();
  mounted = null;
});

function mount(html) {
  mounted = mountAdminPage(html, [THEME_JS]);
  return mounted;
}

describe("admin password toggle (theme.js)", () => {
  it("wraps EVERY plain password input and leaves other fields alone", () => {
    const { doc } = mount(PLAIN_FORM);

    const inputs = doc.querySelectorAll('input[type="password"]');
    expect(inputs.length).toBe(2);
    for (const input of inputs) {
      const wrapper = input.closest(".cusin-password");
      expect(wrapper, `${input.id} must be wrapped`).toBeTruthy();
      expect(wrapper.querySelector(".cusin-password-toggle")).toBeTruthy();
    }
    // A text field is not touched.
    expect(doc.getElementById("id_unrelated").closest(".cusin-password")).toBeNull();
  });

  it("toggles between password and text with the Persian labels", () => {
    const { doc } = mount(PLAIN_FORM);
    const input = doc.getElementById("id_new_password1");
    const button = input.closest(".cusin-password").querySelector(".cusin-password-toggle");

    expect(input.type).toBe("password");
    expect(button.getAttribute("aria-label")).toBe("نمایش رمز");
    expect(button.getAttribute("aria-pressed")).toBe("false");

    button.click();
    expect(input.type).toBe("text");
    expect(button.getAttribute("aria-label")).toBe("پنهان کردن رمز");
    expect(button.getAttribute("aria-pressed")).toBe("true");

    button.click();
    expect(input.type).toBe("password");
    expect(button.getAttribute("aria-label")).toBe("نمایش رمز");
    expect(button.getAttribute("aria-pressed")).toBe("false");
  });

  it("wires the SERVER-RENDERED login markup instead of wrapping it twice", () => {
    const { doc } = mount(LOGIN_FORM);
    const input = doc.getElementById("id_password");
    const button = doc.querySelector(".cusin-password-toggle");

    // No double wrapper, no duplicated buttons.
    expect(doc.querySelectorAll(".cusin-password").length).toBe(1);
    expect(doc.querySelectorAll(".cusin-password-toggle").length).toBe(1);
    expect(button.getAttribute("aria-controls")).toBe("id_password");

    button.click();
    expect(input.type).toBe("text");
    expect(button.getAttribute("aria-pressed")).toBe("true");
    button.click();
    expect(input.type).toBe("password");
  });

  it("never submits the form, in either markup", () => {
    for (const html of [PLAIN_FORM, LOGIN_FORM]) {
      if (mounted) mounted.cleanup();
      const { doc, win } = mount(html);
      const form = doc.querySelector("form");
      const submit = vi.fn((event) => event.preventDefault());
      form.addEventListener("submit", submit);

      doc.querySelector(".cusin-password-toggle").click();

      expect(submit, html).not.toHaveBeenCalled();
      // A real button element, not a submit input.
      expect(doc.querySelector(".cusin-password-toggle").tagName).toBe("BUTTON");
      expect(doc.querySelector(".cusin-password-toggle").getAttribute("type")).toBe("button");
      expect(win.document.querySelectorAll('input[type="submit"]').length).toBeGreaterThan(0);
    }
  });

  it("keeps the value and the caret in the field it belongs to", () => {
    const { doc } = mount(PLAIN_FORM);
    const input = doc.getElementById("id_old_password");
    input.value = "secret-123";

    input.closest(".cusin-password").querySelector(".cusin-password-toggle").click();

    expect(input.value).toBe("secret-123");
    expect(doc.activeElement).toBe(input);
  });

  it("gives both icons a sprite symbol to draw (no emoji, no icon font)", () => {
    const sprite = fs.readFileSync(SPRITE_PATH, "utf8");
    expect(sprite).toContain('id="cusin-i-eye"');
    expect(sprite).toContain('id="cusin-i-eye-off"');

    const { doc } = mount(PLAIN_FORM);
    const button = doc.querySelector(".cusin-password-toggle");
    expect(button.querySelector(".cusin-icon--eye use").getAttribute("href")).toBe("#cusin-i-eye");
    expect(button.querySelector(".cusin-icon--eye-off use").getAttribute("href")).toBe("#cusin-i-eye-off");
  });
});
