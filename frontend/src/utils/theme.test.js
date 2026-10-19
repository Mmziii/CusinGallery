import { afterEach, describe, expect, it } from "vitest";

import {
  applyInitialTheme,
  applyThemeVariables,
  readBootstrapTheme,
} from "./theme";

afterEach(() => {
  document.documentElement.removeAttribute("style");
  delete window.__CUSIN_THEME__;
});

describe("theme variables", () => {
  it("applies custom properties on :root", () => {
    const applied = applyThemeVariables({
      "--color-primary": "#637037",
      "--radius-md": "12px",
    });
    expect(applied).toBe(2);
    const style = document.documentElement.style;
    expect(style.getPropertyValue("--color-primary")).toBe("#637037");
    expect(style.getPropertyValue("--radius-md")).toBe("12px");
  });

  it("ignores non-custom-property names and empty values", () => {
    const applied = applyThemeVariables({
      color: "red",
      "--color-primary": "",
      "--color-text": null,
      "--font-size-base": "1rem",
    });
    expect(applied).toBe(1);
    expect(document.documentElement.style.getPropertyValue("color")).toBe("");
    expect(document.documentElement.style.getPropertyValue("--font-size-base")).toBe("1rem");
  });

  it("reads and applies the variables the Django shell inlined", () => {
    window.__CUSIN_THEME__ = {
      theme: { css_variables: { "--color-primary": "#123456" } },
    };
    expect(readBootstrapTheme()).toEqual({ "--color-primary": "#123456" });
    expect(applyInitialTheme()).toBe(1);
    expect(document.documentElement.style.getPropertyValue("--color-primary")).toBe("#123456");
  });

  it("does nothing when no bootstrap payload exists", () => {
    expect(readBootstrapTheme()).toBeNull();
    expect(applyInitialTheme()).toBe(0);
  });
});
