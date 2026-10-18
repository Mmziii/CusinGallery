import { cleanup, render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";

import Home from "./Home";

afterEach(cleanup);

describe("homepage trust strip", () => {
  it("shows exactly the five requested benefits with line icons", () => {
    const { container } = render(
      <MemoryRouter>
        <Home />
      </MemoryRouter>
    );
    const items = [...container.querySelectorAll(".trust-strip__item")];

    expect(items.map((item) => item.querySelector("span").textContent)).toEqual([
      "تضمین اصالت کالا و سلامت فیزیکی اجناس",
      "بسته‌بندی ضدضربهٔ کالا",
      "ارسال به سراسر ایران",
      "پرداخت امن اینترنتی",
      "امکان تحویل اکسپرس",
    ]);
    items.forEach((item) => expect(item.querySelector("svg.icon")).not.toBeNull());
  });
});
