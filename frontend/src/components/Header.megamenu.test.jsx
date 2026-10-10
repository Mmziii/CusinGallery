/**
 * Mega-menu hover-intent regression tests (Part R1): moving the pointer
 * from the trigger to the panel THROUGH the visual gap must not close the
 * menu (invisible CSS bridge + 200 ms close delay), while leaving the
 * whole area for longer than the delay must close it. Keyboard/touch path
 * (click toggles, Escape closes, aria-expanded correct) is covered too.
 */
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";

import apiClient from "../services/apiClient";
import Header from "./Header";

const TREE = [
  { id: 1, name: "ظروف پخت", slug: "cookware", image: null, children: [{ id: 2, name: "قابلمه", slug: "pot", image: null, children: [] }] },
  { id: 3, name: "بلور", slug: "glass", image: null, children: [] },
];

const originalAdapter = apiClient.defaults.adapter;

beforeAll(() => {
  apiClient.defaults.adapter = async (config) => {
    if (/categories\/tree/.test(config.url || "")) {
      return {
        data: { count: TREE.length, next: null, previous: null, results: TREE },
        status: 200,
        statusText: "OK",
        headers: {},
        config,
      };
    }
    return originalAdapter(config);
  };
});
afterAll(() => {
  apiClient.defaults.adapter = originalAdapter;
});
afterEach(cleanup);

const sleep = (ms) => act(() => new Promise((resolve) => setTimeout(resolve, ms)));

async function renderHeader() {
  render(
    <MemoryRouter initialEntries={["/"]}>
      <Header />
    </MemoryRouter>
  );
  const button = await screen.findByRole("button", { name: /دسته‌بندی کالاها/ });
  return { button, trigger: button.closest(".site-header__mega-trigger") };
}

describe("mega menu", () => {
  it("survives the pointer crossing the gap, closes after the delay when left", async () => {
    const { button, trigger } = await renderHeader();

    fireEvent.mouseEnter(trigger);
    const menu = await waitFor(() => document.querySelector(".mega-menu"));
    expect(button.getAttribute("aria-expanded")).toBe("true");

    // leave the trigger, re-enter the panel through the gap within the
    // hover-intent window -> must stay open
    fireEvent.mouseLeave(trigger);
    await sleep(120); // < 200 ms delay
    fireEvent.mouseEnter(menu);
    await sleep(150);
    expect(document.querySelector(".mega-menu")).not.toBeNull();

    // leaving the whole area for longer than the delay closes it
    fireEvent.mouseLeave(menu);
    await waitFor(() => expect(document.querySelector(".mega-menu")).toBeNull(), { timeout: 1000 });
    expect(button.getAttribute("aria-expanded")).toBe("false");
  });

  it("opens on click/keyboard and closes on Escape (touch-friendly)", async () => {
    const { button } = await renderHeader();
    expect(button.getAttribute("aria-expanded")).toBe("false");

    fireEvent.click(button); // Enter/Space activate buttons as clicks
    await waitFor(() => expect(document.querySelector(".mega-menu")).not.toBeNull());
    expect(button.getAttribute("aria-expanded")).toBe("true");

    fireEvent.keyDown(document, { key: "Escape" });
    await waitFor(() => expect(document.querySelector(".mega-menu")).toBeNull());
    expect(button.getAttribute("aria-expanded")).toBe("false");
  });

  it("links target the category shop filter", async () => {
    const { trigger } = await renderHeader();
    fireEvent.mouseEnter(trigger);
    const allLink = await screen.findByText("همهٔ ظروف پخت");
    expect(allLink.getAttribute("href")).toBe("/shop/?category=cookware");
  });
});
