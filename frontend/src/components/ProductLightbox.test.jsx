import fs from "node:fs";
import path from "node:path";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import ProductGallery from "./ProductGallery";

const images = Array.from({ length: 5 }, (_, index) => ({
  id: index + 1, image: `/media/p${index + 1}.jpg`, alt_text: `تصویر ${index + 1}`,
}));

function openGallery(list = images) {
  const view = render(<ProductGallery images={list} name="قابلمه" />);
  const opener = screen.getByRole("button", { name: "نمایش تصاویر قابلمه" });
  fireEvent.click(opener);
  return { ...view, opener, dialog: screen.getByRole("dialog") };
}

afterEach(() => {
  cleanup();
  document.body.style.overflow = "";
});

describe("full-screen product lightbox", () => {
  it("opens on the selected image, shows a Persian counter and thumbnails, never scales the page image", () => {
    const { container } = render(<ProductGallery images={images} name="قابلمه" />);
    fireEvent.click(screen.getByRole("tab", { name: "تصویر ۲" }));
    fireEvent.click(screen.getByRole("button", { name: "نمایش تصاویر قابلمه" }));
    const dialog = screen.getByRole("dialog");
    expect(dialog.getAttribute("aria-modal")).toBe("true");
    expect(within(dialog).getByRole("status").textContent).toBe("۲ از ۵");
    expect(dialog.querySelector(".product-gallery__layer--active img").getAttribute("src")).toBe("/media/p2.jpg");
    expect(dialog.querySelectorAll(".thumb").length).toBe(5);
    expect(container.querySelector(".is-zoomed")).toBeNull();
    expect(within(dialog).getByRole("img", { name: "تصویر ۲" })).toBeTruthy();
  });

  it("supports both arrow buttons, RTL keyboard arrows and thumbnail selection", () => {
    const { dialog } = openGallery();
    fireEvent.click(within(dialog).getByRole("button", { name: "تصویر بعدی" }));
    expect(within(dialog).getByRole("status").textContent).toBe("۲ از ۵");
    fireEvent.click(within(dialog).getByRole("button", { name: "تصویر قبلی" }));
    expect(within(dialog).getByRole("status").textContent).toBe("۱ از ۵");
    fireEvent.keyDown(document, { key: "ArrowLeft" });
    expect(within(dialog).getByRole("status").textContent).toBe("۲ از ۵");
    fireEvent.keyDown(document, { key: "ArrowRight" });
    expect(within(dialog).getByRole("status").textContent).toBe("۱ از ۵");
    fireEvent.click(within(dialog).getByRole("button", { name: "نمایش تصویر ۵" }));
    expect(within(dialog).getByRole("status").textContent).toBe("۵ از ۵");
    fireEvent.keyDown(document, { key: "ArrowLeft" });
    expect(within(dialog).getByRole("status").textContent).toBe("۱ از ۵");
  });

  it("supports horizontal touch swipes but ignores vertical scrolling and cancelled gestures", () => {
    const { dialog } = openGallery();
    const stage = dialog.querySelector(".product-lightbox__stage");
    const swipe = (endX, endY) => {
      fireEvent.touchStart(stage, { touches: [{ clientX: 200, clientY: 200 }] });
      fireEvent.touchEnd(stage, { changedTouches: [{ clientX: endX, clientY: endY }] });
    };
    swipe(100, 205);
    expect(within(dialog).getByRole("status").textContent).toBe("۲ از ۵");
    swipe(300, 205);
    expect(within(dialog).getByRole("status").textContent).toBe("۱ از ۵");
    swipe(100, 400);
    expect(within(dialog).getByRole("status").textContent).toBe("۱ از ۵");
    fireEvent.touchStart(stage, { touches: [{ clientX: 200, clientY: 200 }] });
    fireEvent.touchCancel(stage);
    fireEvent.touchEnd(stage, { changedTouches: [{ clientX: 100, clientY: 200 }] });
    expect(within(dialog).getByRole("status").textContent).toBe("۱ از ۵");
  });

  it("locks scrolling, isolates the background, traps focus, closes with Escape and restores focus", () => {
    document.body.style.overflow = "auto";
    const { container, opener, dialog } = openGallery();
    const close = within(dialog).getByRole("button", { name: "بستن تصاویر" });
    expect(document.activeElement).toBe(close);
    expect(document.body.style.overflow).toBe("hidden");
    expect(document.documentElement.style.overflow).toBe("hidden");
    expect(container.hasAttribute("inert")).toBe(true);
    const last = within(dialog).getByRole("button", { name: "نمایش تصویر ۵" });
    last.focus();
    fireEvent.keyDown(document, { key: "Tab" });
    expect(document.activeElement).toBe(close);
    fireEvent.keyDown(document, { key: "Tab", shiftKey: true });
    expect(document.activeElement).toBe(last);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(opener);
    expect(document.body.style.overflow).toBe("auto");
    expect(document.documentElement.style.overflow).toBe("");
    expect(container.hasAttribute("inert")).toBe(false);
  });

  it("closes with its close button or backdrop and restores focus each time", () => {
    const { opener, dialog } = openGallery();
    fireEvent.click(within(dialog).getByRole("button", { name: "بستن تصاویر" }));
    expect(document.activeElement).toBe(opener);
    fireEvent.click(opener);
    fireEvent.click(screen.getByRole("dialog"));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(opener);
  });

  it("cleans up scroll locks and background isolation when unmounted while open", () => {
    const { container, unmount } = openGallery();
    unmount();
    expect(document.body.style.overflow).toBe("");
    expect(document.documentElement.style.overflow).toBe("");
    expect(container.hasAttribute("inert")).toBe(false);
  });

  it("works for a single image without arrows or a redundant thumbnail strip", () => {
    const { dialog } = openGallery([images[0]]);
    expect(within(dialog).getByRole("status").textContent).toBe("۱ از ۱");
    expect(within(dialog).queryByRole("button", { name: "تصویر بعدی" })).toBeNull();
    expect(within(dialog).queryByRole("button", { name: "تصویر قبلی" })).toBeNull();
    expect(dialog.querySelector(".thumb")).toBeNull();
    fireEvent.keyDown(document, { key: "ArrowLeft" });
    expect(within(dialog).getByRole("status").textContent).toBe("۱ از ۱");
  });

  it.each([{ list: [] }, { list: [{ id: 1, image: null }] }])("does not offer a popup without images ($list)", ({ list }) => {
    const { container } = render(<ProductGallery images={list} name="قابلمه" />);
    expect(screen.queryByRole("button", { name: "نمایش تصاویر قابلمه" })).toBeNull();
    fireEvent.click(container.querySelector(".product-gallery__stage"));
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("respects reduced motion and keeps the image contained in a viewport-sized dialog", () => {
    const css = fs.readFileSync(path.resolve(__dirname, "../styles/storefront.css"), "utf8");
    expect(css).toMatch(/\.product-lightbox\s*\{[^}]*position: fixed;[^}]*height: 100dvh/);
    expect(css).toMatch(/@media \(prefers-reduced-motion: reduce\)\s*\{\s*\.product-lightbox, \.product-lightbox__stage \.product-gallery__layer--active \{ animation: none/);
    expect(css).not.toContain(".is-zoomed");
  });
});
