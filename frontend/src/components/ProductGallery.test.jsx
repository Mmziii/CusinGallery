/**
 * Part S5 item 3: the product gallery.
 *
 * Verifies the behaviour the owner asked for: thumbnails under the main
 * image, selection by click and by keyboard (ARIA tablist, RTL-aware arrow
 * keys), the cross-fade layer swap, swipe support, no thumbnail row for a
 * single-image product, and the shared placeholder for broken thumbnails.
 */
import { act, cleanup, fireEvent, render, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import ProductGallery from "./ProductGallery";

const image = (id) => ({
  id,
  image: `/media/p${id}.jpg`,
  alt_text: `تصویر ${id}`,
  is_primary: id === 1,
  ordering: id,
});

const THREE = [image(1), image(2), image(3)];

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("ProductGallery thumbnails (Part S5 item 3)", () => {
  it("shows the main image plus a thumbnail per image, marking the active one", () => {
    const { container } = render(<ProductGallery images={THREE} name="قابلمه" />);

    const thumbs = container.querySelectorAll(".thumb");
    expect(thumbs.length).toBe(3);
    expect(thumbs[0].classList.contains("thumb--active")).toBe(true);
    expect(thumbs[0].getAttribute("aria-selected")).toBe("true");
    expect(thumbs[0].getAttribute("tabindex")).toBe("0");
    expect(thumbs[1].getAttribute("tabindex")).toBe("-1");
    expect(container.querySelector(".product-gallery__layer--active img").getAttribute("src")).toBe(
      "/media/p1.jpg"
    );
  });

  it("selects by click and keeps the previous image during the cross-fade", () => {
    vi.useFakeTimers();
    const { container } = render(<ProductGallery images={THREE} name="قابلمه" />);

    fireEvent.click(container.querySelectorAll(".thumb")[2]);

    // The new image is already the active layer...
    expect(container.querySelector(".product-gallery__layer--active img").getAttribute("src")).toBe(
      "/media/p3.jpg"
    );
    // ...and the old one is still rendered underneath, fading out.
    const leaving = container.querySelector(".product-gallery__layer--leaving img");
    expect(leaving.getAttribute("src")).toBe("/media/p1.jpg");
    // After the ~200ms fade the leaving layer is dropped (no extra DOM).
    act(() => {
      vi.advanceTimersByTime(300);
    });
    expect(container.querySelector(".product-gallery__layer--leaving")).toBeNull();
  });

  it("is keyboard operable: RTL arrow keys, Home and End move the selection and the focus", async () => {
    const { container } = render(<ProductGallery images={THREE} name="قابلمه" />);
    const list = container.querySelector('[role="tablist"]');
    const thumbs = () => container.querySelectorAll(".thumb");

    // ArrowLeft = next in an RTL row.
    fireEvent.keyDown(list, { key: "ArrowLeft" });
    await waitFor(() => expect(thumbs()[1].classList.contains("thumb--active")).toBe(true));
    expect(document.activeElement).toBe(thumbs()[1]);

    // ArrowRight = previous.
    fireEvent.keyDown(list, { key: "ArrowRight" });
    await waitFor(() => expect(thumbs()[0].classList.contains("thumb--active")).toBe(true));

    fireEvent.keyDown(list, { key: "End" });
    await waitFor(() => expect(thumbs()[2].classList.contains("thumb--active")).toBe(true));
    fireEvent.keyDown(list, { key: "Home" });
    await waitFor(() => expect(thumbs()[0].classList.contains("thumb--active")).toBe(true));
    expect(document.activeElement).toBe(thumbs()[0]);
  });

  it("supports swipe on the main image", async () => {
    const { container } = render(<ProductGallery images={THREE} name="قابلمه" />);
    const stage = container.querySelector(".product-gallery__stage");
    const thumbs = () => container.querySelectorAll(".thumb");

    fireEvent.touchStart(stage, { touches: [{ clientX: 300 }] });
    fireEvent.touchEnd(stage, { changedTouches: [{ clientX: 200 }] });
    await waitFor(() => expect(thumbs()[1].classList.contains("thumb--active")).toBe(true));

    fireEvent.touchStart(stage, { touches: [{ clientX: 200 }] });
    fireEvent.touchEnd(stage, { changedTouches: [{ clientX: 300 }] });
    await waitFor(() => expect(thumbs()[0].classList.contains("thumb--active")).toBe(true));
  });

  it("renders no thumbnail row for a single-image product", () => {
    const { container } = render(<ProductGallery images={[image(1)]} name="قابلمه" />);
    expect(container.querySelector('[role="tablist"]')).toBeNull();
    expect(container.querySelector(".thumb")).toBeNull();
    expect(container.querySelector(".product-gallery__layer--active img")).not.toBeNull();
  });

  it("keeps zoom working and resets it when the image changes", async () => {
    const { container } = render(<ProductGallery images={THREE} name="قابلمه" />);
    const stage = container.querySelector(".product-gallery__stage");

    fireEvent.click(stage);
    expect(container.querySelector(".product-gallery__layer--active img.is-zoomed")).not.toBeNull();

    fireEvent.click(container.querySelectorAll(".thumb")[1]);
    await waitFor(() =>
      expect(container.querySelector(".product-gallery__layer--active img.is-zoomed")).toBeNull()
    );
  });

  it("falls back to the shared placeholder when an image is missing or broken", () => {
    const broken = [{ ...image(1), image: "/media/gone.jpg" }, image(2)];
    const { container } = render(<ProductGallery images={broken} name="قابلمه" />);

    const main = container.querySelector(".product-gallery__layer--active img");
    fireEvent.error(main);
    expect(container.querySelector(".product-gallery__layer--active .img-placeholder__mark")).not.toBeNull();

    // A broken thumbnail uses the same placeholder instead of a broken icon.
    const thumbImg = container.querySelectorAll(".thumb img")[1];
    fireEvent.error(thumbImg);
    expect(container.querySelectorAll(".thumb")[1].querySelector(".img-placeholder__mark")).not.toBeNull();
  });

  it("shows the placeholder when the product has no images at all", () => {
    const { container } = render(<ProductGallery images={[]} name="قابلمه" />);
    expect(container.querySelector(".img-placeholder__mark")).not.toBeNull();
    expect(container.querySelector('[role="tablist"]')).toBeNull();
  });
});
