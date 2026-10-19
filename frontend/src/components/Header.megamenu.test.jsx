/**
 * Mega-menu tests (Part R1 hover-intent + Stage 2 Digikala
 * rebuild):
 *
 *  - hover opens with a ~150 ms intent delay (no flicker),
 *    the panel survives the pointer crossing the gap to it,
 *    and closes ~200 ms after the pointer leaves the whole
 *    area (invisible CSS bridge + close grace);
 *  - click/Enter opens it for touch laptops and keyboard
 *    users, Escape closes it and returns focus to the
 *    trigger;
 *  - the desktop panel is Digikala-shaped: a «همهٔ محصولات
 *    <category> ›» link on top, sub-categories as bold
 *    headings (with «›») in columns, their children under
 *    them, the active main category highlighted;
 *  - empty categories (no active products in the whole
 *    subtree) never show up;
 *  - under 1024px the button opens a full-height sheet
 *    with drill-down navigation («بازگشت» back arrow,
 *    «مشاهدهٔ همه» on every level) and locks the
 *    body scroll.
 */
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";

import apiClient from "../services/apiClient";
import Header from "./Header";
import MegaMenu from "./MegaMenu";

const TREE = [
  {
    id: 1,
    name: "ظروف پخت",
    slug: "cookware",
    image: null,
    product_count: 3,
    children: [
      {
        id: 2,
        name: "قابلمه",
        slug: "pot",
        image: null,
        product_count: 2,
        children: [
          { id: 5, name: "قابلمه گرانیتی", slug: "granite-pot", image: null, product_count: 2, children: [] },
        ],
      },
    ],
  },
  { id: 3, name: "بلور", slug: "glass", image: null, product_count: 1, children: [] },
  // Empty in its whole subtree: must be hidden.
  {
    id: 4,
    name: "بایگانی",
    slug: "archive",
    image: null,
    product_count: 0,
    children: [{ id: 6, name: "قدیمی", slug: "old", image: null, product_count: 0, children: [] }],
  },
];

const originalAdapter = apiClient.defaults.adapter;

beforeAll(() => {
  apiClient.defaults.adapter = async (config) => {
    if (/categories\/tree/.test(config.url || "")) {
      return {
        data: { count: 1, next: null, previous: null, results: [{ id: 99, name: "آشپزخانه", slug: "kitchen-root", is_catalog_root: true, children: TREE }] },
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
  const view = render(
    <MemoryRouter initialEntries={["/"]}>
      <Header />
    </MemoryRouter>
  );
  const button = await screen.findByRole("button", { name: /دسته‌بندی کالاها/ });
  return { view, button, trigger: button.closest(".site-header__mega-trigger") };
}

// waitFor only retries when the callback THROWS -- assert
// inside it so a not-yet-open menu actually waits.
const untilMenu = () =>
  waitFor(() => {
    const menu = document.querySelector(".mega-menu");
    expect(menu).toBeTruthy();
    return menu;
  });

describe("mega menu", () => {
  it("opens the real root's groups even when its slug is kitchen-root", async () => {
    const { button } = await renderHeader();
    fireEvent.click(button);
    await untilMenu();
    const roots = document.querySelector(".mega-menu__roots");
    expect(within(roots).getAllByRole("button").map((item) => item.textContent.trim())).toEqual(["ظروف پخت", "بلور"]);
  });

  it("survives the pointer crossing the gap, closes after the delay when left", async () => {
    const { button, trigger } = await renderHeader();

    fireEvent.mouseEnter(trigger);
    // Hover intent: not open instantly, but open after
    // the ~150 ms delay.
    await sleep(60);
    expect(document.querySelector(".mega-menu")).toBeNull();
    await untilMenu();
    expect(button.getAttribute("aria-expanded")).toBe("true");

    // leave the trigger, re-enter the panel through the
    // gap within the close grace -> must stay open
    fireEvent.mouseLeave(trigger);
    await sleep(120); // < 200 ms grace
    fireEvent.mouseEnter(document.querySelector(".mega-menu"));
    await sleep(150);
    expect(document.querySelector(".mega-menu")).not.toBeNull();

    // leaving the whole area for longer than the grace
    // closes it
    fireEvent.mouseLeave(document.querySelector(".mega-menu"));
    await waitFor(() => expect(document.querySelector(".mega-menu")).toBeNull(), { timeout: 1000 });
    expect(button.getAttribute("aria-expanded")).toBe("false");
  });

  it("closes when the dimmed page overlay is clicked", async () => {
    const { button, trigger } = await renderHeader();
    fireEvent.mouseEnter(trigger);
    await untilMenu();

    const overlay = document.querySelector(".mega-menu__overlay");
    expect(overlay).not.toBeNull();
    expect(trigger.contains(overlay)).toBe(false);

    fireEvent.click(overlay);
    await waitFor(() => expect(document.querySelector(".mega-menu")).toBeNull());
    expect(button.getAttribute("aria-expanded")).toBe("false");
  });

  it("closes after the 200ms grace when the pointer leaves the panel for the page", async () => {
    const { button, trigger } = await renderHeader();
    fireEvent.mouseEnter(trigger);
    await untilMenu();

    const panel = document.querySelector(".mega-menu");
    const overlay = document.querySelector(".mega-menu__overlay");
    fireEvent.mouseLeave(panel, { relatedTarget: overlay });

    await sleep(80);
    expect(document.querySelector(".mega-menu")).not.toBeNull();
    await waitFor(() => expect(document.querySelector(".mega-menu")).toBeNull(), { timeout: 1000 });
    expect(button.getAttribute("aria-expanded")).toBe("false");
  });

  it("opens on click/keyboard and closes on Escape (touch-friendly)", async () => {
    const { button, view } = await renderHeader();
    expect(button.getAttribute("aria-expanded")).toBe("false");

    fireEvent.click(button); // Enter/Space activate buttons as clicks
    await untilMenu();
    expect(button.getAttribute("aria-expanded")).toBe("true");

    fireEvent.keyDown(document, { key: "Escape" });
    await waitFor(() => expect(view.container.querySelector(".mega-menu")).toBeNull());
    expect(button.getAttribute("aria-expanded")).toBe("false");
  });

  it("links target the category shop filter", async () => {
    const { trigger } = await renderHeader();
    fireEvent.mouseEnter(trigger);
    const allLink = await screen.findByText("همهٔ محصولات ظروف پخت");
    expect(allLink.closest("a").getAttribute("href")).toBe("/shop/?category=cookware");
  });

  it("lays out the panel Digikala-style: all-link on top, sub-category headings with children in columns", async () => {
    const { trigger, view } = await renderHeader();
    fireEvent.mouseEnter(trigger);
    await untilMenu();

    const panel = view.container.querySelector(".mega-menu__panel");
    // «همهٔ محصولات <category> ›» leads the panel.
    const all = panel.querySelector(".mega-menu__all");
    expect(all.textContent).toContain("همهٔ محصولات ظروف پخت");

    // Each sub-category is a bold heading ending in «›»
    // with its children listed under it.
    const subhead = panel.querySelector(".mega-menu__subhead");
    expect(subhead.textContent).toContain("قابلمه");
    expect(subhead.textContent).toContain("›");
    const childLink = within(panel).getByRole("link", { name: "قابلمه گرانیتی" });
    expect(childLink.getAttribute("href")).toBe("/shop/?category=granite-pot");

    // Main categories live in the roots column, with the
    // first one active by default.
    const roots = view.container.querySelector(".mega-menu__roots");
    const rootButtons = within(roots).getAllByRole("button");
    expect(rootButtons.length).toBe(2); // the empty group is hidden
    expect(rootButtons[0].className).toContain("is-active");
  });

  it("switches the panel content when another main category is hovered", async () => {
    const { trigger, view } = await renderHeader();
    fireEvent.mouseEnter(trigger);
    await untilMenu();

    const roots = view.container.querySelector(".mega-menu__roots");
    const glass = within(roots).getByRole("button", { name: /بلور/ });
    fireEvent.mouseEnter(glass);

    const panel = view.container.querySelector(".mega-menu__panel");
    await waitFor(() =>
      expect(panel.querySelector(".mega-menu__all").textContent).toContain("همهٔ محصولات بلور")
    );
    expect(glass.className).toContain("is-active");
  });

  it("hides categories with no active products in the whole subtree", async () => {
    const { trigger, view } = await renderHeader();
    fireEvent.mouseEnter(trigger);
    await untilMenu();

    const roots = view.container.querySelector(".mega-menu__roots");
    expect(within(roots).queryByRole("button", { name: /بایگانی/ })).toBeNull();
    expect(view.container.textContent).not.toContain("قدیمی");
  });

  it("supports arrow keys within the main-category list", async () => {
    const { view } = await renderHeader();
    fireEvent.click(await screen.findByRole("button", { name: /دسته‌بندی کالاها/ }));
    await untilMenu();

    const roots = view.container.querySelector(".mega-menu__roots");
    const [first, second] = within(roots).getAllByRole("button");
    first.focus();
    fireEvent.keyDown(roots, { key: "ArrowDown" });
    expect(document.activeElement).toBe(second);
    fireEvent.keyDown(roots, { key: "ArrowUp" });
    expect(document.activeElement).toBe(first);
  });
});

describe("mega menu mobile sheet", () => {
  function renderMegaOnly() {
    const view = render(
      <MemoryRouter initialEntries={["/"]}>
        <MegaMenu
          groups={[
            {
              id: 1,
              name: "ظروف پخت",
              slug: "cookware",
              image: null,
              product_count: 2,
              children: [
                { id: 2, name: "قابلمه", slug: "pot", image: null, product_count: 1, children: [] },
              ],
            },
            { id: 3, name: "بلور", slug: "glass", image: null, product_count: 1, children: [] },
          ]}
          open={false}
          onOpen={() => {}}
          onClose={() => {}}
        />
      </MemoryRouter>
    );
    return view;
  }

  it("drills down with a back arrow and a per-level all-link", async () => {
    const view = renderMegaOnly();
    // The sheet is driven by `open` -- drive it through a
    // controlled re-render.
    const { rerender } = view;
    const groups = [
      {
        id: 1,
        name: "ظروف پخت",
        slug: "cookware",
        image: null,
        product_count: 2,
        children: [
          { id: 2, name: "قابلمه", slug: "pot", image: null, product_count: 1, children: [] },
        ],
      },
      { id: 3, name: "بلور", slug: "glass", image: null, product_count: 1, children: [] },
    ];
    rerender(
      <MemoryRouter initialEntries={["/"]}>
        <MegaMenu groups={groups} open onOpen={() => {}} onClose={() => {}} />
      </MemoryRouter>
    );

    const sheet = await screen.findByRole("dialog", { name: "دسته‌بندی کالاها" });
    // Every level starts with «مشاهدهٔ همه».
    const all = within(sheet).getByRole("link", { name: /مشاهدهٔ همه/ });
    expect(all.getAttribute("href")).toBe("/shop/");

    // Main groups are listed; a group with children is a
    // drill button, a leaf is a direct link.
    const drill = within(sheet).getByRole("button", { name: /ظروف پخت/ });
    const leaf = within(sheet).getByRole("link", { name: "بلور" });
    expect(leaf.getAttribute("href")).toBe("/shop/?category=glass");

    // Drill down: the children slide in with a back
    // arrow and the group's title.
    fireEvent.click(drill);
    await waitFor(() => {
      expect(within(sheet).getByRole("button", { name: /بازگشت/ })).toBeTruthy();
    });
    expect(within(sheet).getByRole("heading", { name: "ظروف پخت" })).toBeTruthy();
    const childLink = within(sheet).getByRole("link", { name: "قابلمه" });
    expect(childLink.getAttribute("href")).toBe("/shop/?category=pot");
    const levelAll = within(sheet).getByRole("link", {
      name: /مشاهدهٔ همه ظروف پخت/,
    });
    expect(levelAll.getAttribute("href")).toBe("/shop/?category=cookware");

    // «بازگشت» returns to the top level.
    fireEvent.click(within(sheet).getByRole("button", { name: /بازگشت/ }));
    await waitFor(() => {
      expect(within(sheet).queryByRole("button", { name: /بازگشت/ })).toBeNull();
    });
  });

  it("handles touch tap to drill down into subcategories without closing, ignoring scroll gestures", async () => {
    let openState = true;
    const groups = [
      {
        id: 1,
        name: "ظروف پخت",
        slug: "cookware",
        image: null,
        product_count: 2,
        children: [
          { id: 2, name: "قابلمه", slug: "pot", image: null, product_count: 1, children: [] },
        ],
      },
    ];

    render(
      <MemoryRouter initialEntries={["/"]}>
        <MegaMenu
          groups={groups}
          open={openState}
          onOpen={() => { openState = true; }}
          onClose={() => { openState = false; }}
        />
      </MemoryRouter>
    );

    const sheet = await screen.findByRole("dialog", { name: "دسته‌بندی کالاها" });
    const drill = within(sheet).getByRole("button", { name: /ظروف پخت/ });

    // 1. A scroll gesture (dy > 12) should NOT drill down
    fireEvent.touchStart(drill, { touches: [{ clientX: 100, clientY: 100 }] });
    fireEvent.touchEnd(drill, { changedTouches: [{ clientX: 100, clientY: 150 }] });
    expect(within(sheet).queryByRole("button", { name: /بازگشت/ })).toBeNull();
    expect(openState).toBe(true);

    // 2. A genuine tap (dx < 12, dy < 12) drills down and remains open
    fireEvent.touchStart(drill, { touches: [{ clientX: 100, clientY: 100 }] });
    fireEvent.touchEnd(drill, { changedTouches: [{ clientX: 102, clientY: 101 }] });

    await waitFor(() => {
      expect(within(sheet).getByRole("button", { name: /بازگشت/ })).toBeTruthy();
    });
    expect(within(sheet).getByRole("heading", { name: "ظروف پخت" })).toBeTruthy();
    expect(openState).toBe(true);

    // 3. Tapping back returns to parent level and remains open
    const back = within(sheet).getByRole("button", { name: /بازگشت/ });
    fireEvent.touchStart(back, { touches: [{ clientX: 50, clientY: 50 }] });
    fireEvent.touchEnd(back, { changedTouches: [{ clientX: 51, clientY: 51 }] });

    await waitFor(() => {
      expect(within(sheet).queryByRole("button", { name: /بازگشت/ })).toBeNull();
    });
    expect(openState).toBe(true);
  });

  it("locks the body scroll while open (through the header)", async () => {
    // The document lock is owned by the header (it is
    // shared by all full-viewport surfaces), so this
    // runs against the real <Header/>.
    const { button } = await renderHeader();
    fireEvent.click(button);
    await screen.findByRole("dialog", { name: "دسته‌بندی کالاها" });
    expect(document.body.classList.contains("body--scroll-locked")).toBe(true);

    // Close via the sheet's own close button.
    fireEvent.click(screen.getByRole("button", { name: "بستن دسته‌بندی‌ها" }));
    await waitFor(() => {
      expect(
        document.body.classList.contains("body--scroll-locked")
      ).toBe(false);
    });
  });
});
