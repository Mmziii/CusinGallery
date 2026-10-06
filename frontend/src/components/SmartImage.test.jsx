/**
 * SmartImage placeholder tests (Part R1): a product without an image and a
 * product image that fails to load must both render the shared brand
 * placeholder in the image area (never a broken <img> or a layout shift).
 */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import SmartImage from "./SmartImage";

afterEach(cleanup);

describe("SmartImage placeholder", () => {
  it("renders the placeholder when there is no image at all", () => {
    const { container } = render(<SmartImage image={null} alt="قابلمه" />);
    expect(container.querySelector("img")).toBeNull();
    const placeholder = container.querySelector(".img-placeholder");
    expect(placeholder).not.toBeNull();
    expect(placeholder.getAttribute("aria-label")).toBe("قابلمه");
    expect(placeholder.querySelector(".img-placeholder__mark")).not.toBeNull();
  });

  it("renders the placeholder when the image URL fails to load", () => {
    const { container } = render(
      <SmartImage image={{ image: "http://localhost/definitely-missing.jpg" }} alt="سرویس" />
    );
    const img = container.querySelector("img");
    expect(img).not.toBeNull();
    fireEvent.error(img); // network 404 / broken file
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector(".img-placeholder")).not.toBeNull();
  });

  it("renders a real image when one exists", () => {
    render(<SmartImage image={{ image: "/media/ok.jpg" }} alt="خوب" />);
    const img = screen.getByAltText("خوب");
    expect(img.getAttribute("src")).toBe("/media/ok.jpg");
  });

  it("uses responsive webp variants when provided", () => {
    const { container } = render(
      <SmartImage
        image={{ image: "/media/ok.jpg", webp_400: "/media/ok-400.webp", webp_800: "/media/ok-800.webp" }}
        alt="وب‌پ"
      />
    );
    const source = container.querySelector("source");
    expect(source.getAttribute("srcset")).toContain("/media/ok-400.webp 400w");
  });
});
