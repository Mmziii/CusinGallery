/**
 * Audit 19 item 3: the password visibility toggle.
 *
 * One reusable <PasswordInput /> for every storefront password field. These
 * tests pin the contract the owner asked for -- eye button inside the field
 * on the LEFT (inline end) side of an RTL form, tap = text, tap again =
 * password, eye / eye-off icons, the Persian aria-labels, aria-pressed, a
 * 40px tap target and `type="button"` so it can never submit the form -- and
 * then check that no page still hand-rolls a plain `type="password"` input.
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import PasswordInput from "./PasswordInput";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SRC = path.resolve(HERE, "..");
const CSS = fs.readFileSync(path.join(SRC, "styles", "storefront.css"), "utf8").replace(/\s+/g, " ");

afterEach(cleanup);

describe("PasswordInput", () => {
  it("starts hidden and toggles to a visible text field and back", () => {
    const { container } = render(
      <label className="field">
        <span>رمز عبور</span>
        <PasswordInput value="secret123" onChange={() => {}} />
      </label>
    );

    const input = container.querySelector("input");
    const toggle = screen.getByRole("button", { name: "نمایش رمز" });

    expect(input.type).toBe("password");
    expect(input.value).toBe("secret123");
    expect(toggle.getAttribute("aria-pressed")).toBe("false");

    fireEvent.click(toggle);
    expect(container.querySelector("input").type).toBe("text");
    expect(screen.getByRole("button", { name: "پنهان کردن رمز" }).getAttribute("aria-pressed")).toBe("true");

    fireEvent.click(screen.getByRole("button", { name: "پنهان کردن رمز" }));
    expect(container.querySelector("input").type).toBe("password");
    expect(screen.getByRole("button", { name: "نمایش رمز" }).getAttribute("aria-pressed")).toBe("false");
  });

  it("swaps the eye / eye-off icon and never swallows the value", () => {
    const { container } = render(<PasswordInput value="abc" onChange={() => {}} />);
    const iconName = () => container.querySelector(".password-field__toggle .icon use, .password-field__toggle .icon").innerHTML;

    const hidden = iconName();
    fireEvent.click(screen.getByRole("button", { name: "نمایش رمز" }));
    expect(iconName()).not.toBe(hidden); // eye -> eye-off
    expect(container.querySelector("input").value).toBe("abc");
  });

  it("is a plain button, so tapping it never submits the form", () => {
    const onSubmit = vi.fn((event) => event.preventDefault());
    render(
      <form onSubmit={onSubmit}>
        <PasswordInput value="abc" onChange={() => {}} />
      </form>
    );

    const toggle = screen.getByRole("button", { name: "نمایش رمز" });
    expect(toggle.getAttribute("type")).toBe("button");
    fireEvent.click(toggle);

    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "پنهان کردن رمز" })).toBeTruthy();
  });

  it("forwards the input props the pages rely on", () => {
    const onChange = vi.fn();
    const { container } = render(
      <PasswordInput
        id="pw-current"
        name="current_password"
        autoComplete="current-password"
        aria-invalid="true"
        required
        disabled
        dir="ltr"
        value=""
        onChange={onChange}
      />
    );
    const input = container.querySelector("input");

    expect(input.id).toBe("pw-current");
    expect(input.name).toBe("current_password");
    expect(input.getAttribute("autocomplete")).toBe("current-password");
    expect(input.getAttribute("aria-invalid")).toBe("true");
    expect(input.hasAttribute("required")).toBe(true);
    expect(input.disabled).toBe(true);
    expect(input.getAttribute("dir")).toBe("ltr");
    // The toggle points at the field it controls, for screen readers.
    expect(screen.getByRole("button").getAttribute("aria-controls")).toBe("pw-current");
    fireEvent.change(input, { target: { value: "x" } });
    expect(onChange).toHaveBeenCalled();
  });

  it("keeps a 40px tap target at the inline end (the LEFT side in RTL)", () => {
    expect(CSS).toMatch(/\.password-field__toggle \{[^}]*width: 40px; height: 40px;/);
    expect(CSS).toMatch(/\.password-field__toggle \{[^}]*inset-inline-end: 4px;/);
    // The input reserves room for the button so text never runs under it.
    expect(CSS).toMatch(/\.password-field__input \{[^}]*padding-inline-end: 46px;/);
  });
});

describe("every storefront password field uses PasswordInput", () => {
  const walk = (dir) =>
    fs.readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) return walk(full);
      return /\.jsx?$/.test(entry.name) ? [full] : [];
    });

  it("no page renders a raw type=\"password\" input any more", () => {
    const offenders = walk(SRC)
      .filter((file) => !file.includes(".test."))
      .filter((file) => !file.endsWith("PasswordInput.jsx"))
      .filter((file) => /type="password"/.test(fs.readFileSync(file, "utf8")))
      .map((file) => path.relative(SRC, file));

    expect(offenders).toEqual([]);
  });

  it("login, register, reset-confirm and the account all import the component", () => {
    for (const file of [
      "pages/LoginPage.jsx",
      "pages/RegisterPage.jsx",
      "pages/PasswordResetConfirmPage.jsx",
      "pages/account/ProfilePage.jsx",
    ]) {
      const source = fs.readFileSync(path.join(SRC, file), "utf8");
      expect(source, file).toContain("PasswordInput");
    }
  });
});
