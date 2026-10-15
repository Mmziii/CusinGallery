import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { expect, it } from "vitest";
import ProductCard from "./ProductCard";
it("reserves a brand line even for unbranded products", () => {
 const { container } = render(<MemoryRouter><ProductCard product={{ id: 1, name: "نام طولانی ".repeat(12), slug: "long", price_info: {price: 100} }} /></MemoryRouter>);
 expect(container.querySelector(".product-card__brand")).toBeTruthy();
 expect(container.querySelector(".product-card__name").textContent).toContain("نام طولانی");
});
