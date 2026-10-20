import { afterEach, describe, expect, it } from "vitest";

import { mountAdminPage, readAdminScript } from "../test/adminFrame";

let mounted = null;
const SCRIPT = () => readAdminScript("jalali_datepicker.js");

afterEach(() => {
  mounted?.cleanup();
  mounted = null;
});

async function mount(html = '<div class="form-row"><input id="id_date" data-jalali-date="true" value="۱۴۰۵/۰۷/۲۷"></div>') {
  mounted = mountAdminPage(html, [SCRIPT()]);
  await new Promise((resolve) => setTimeout(resolve, 0));
  return mounted.doc;
}

function rect({ left, right, top, bottom, width, height }) {
  return { left, right, top, bottom, width, height, x: left, y: top, toJSON: () => ({}) };
}

describe("Jalali date picker", () => {
  it("portals to body, positions by the input, and writes selected Persian digits", async () => {
    const doc = await mount();
    const input = doc.getElementById("id_date");
    const button = doc.querySelector(".jalali-date-open");
    const popup = doc.getElementById(button.getAttribute("aria-controls"));

    expect(button.querySelector("use").getAttribute("href")).toBe("#cusin-i-calendar");
    expect(popup.parentElement).toBe(doc.body);
    input.getBoundingClientRect = () => rect({ left: 100, right: 450, top: 200, bottom: 230, width: 350, height: 30 });
    popup.getBoundingClientRect = () => rect({ left: 0, right: 280, top: 0, bottom: 320, width: 280, height: 320 });

    button.click();
    expect(popup.hidden).toBe(false);
    expect(popup.style.position).toBe("fixed");
    expect(popup.style.left).toBe("170px");
    expect(popup.style.top).toBe("234px");

    popup.querySelector('[aria-label="۱۴۰۵/۰۷/۰۱"]').click();
    expect(input.value).toBe("۱۴۰۵/۰۷/۰۱");
    expect(popup.hidden).toBe(true);
  });

  it("flips above the input when the popup will not fit below it", async () => {
    const doc = await mount();
    const button = doc.querySelector(".jalali-date-open");
    const input = doc.getElementById("id_date");
    const popup = doc.getElementById(button.getAttribute("aria-controls"));
    mounted.win.innerHeight = 700;
    input.getBoundingClientRect = () => rect({ left: 100, right: 450, top: 600, bottom: 630, width: 350, height: 30 });
    popup.getBoundingClientRect = () => rect({ left: 0, right: 280, top: 0, bottom: 320, width: 280, height: 320 });

    button.click();

    expect(popup.style.top).toBe("276px");
  });

  it("anchors repositioning to scroll and resize and closes on Escape or outside click", async () => {
    const doc = await mount();
    const button = doc.querySelector(".jalali-date-open");
    const input = doc.getElementById("id_date");
    const popup = doc.getElementById(button.getAttribute("aria-controls"));
    let top = 100;
    input.getBoundingClientRect = () => rect({ left: 100, right: 450, top, bottom: top + 30, width: 350, height: 30 });
    popup.getBoundingClientRect = () => rect({ left: 0, right: 280, top: 0, bottom: 320, width: 280, height: 320 });

    button.click();
    top = 180;
    mounted.win.dispatchEvent(new mounted.win.Event("scroll"));
    expect(popup.style.top).toBe("214px");
    doc.dispatchEvent(new mounted.win.KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    expect(popup.hidden).toBe(true);

    button.click();
    doc.body.dispatchEvent(new mounted.win.MouseEvent("click", { bubbles: true }));
    expect(popup.hidden).toBe(true);
  });

  it("uses a full-width bottom sheet on phone-sized viewports", async () => {
    const doc = await mount();
    const button = doc.querySelector(".jalali-date-open");
    const popup = doc.getElementById(button.getAttribute("aria-controls"));
    mounted.win.innerWidth = 390;
    button.click();

    expect(popup.classList.contains("jalali-date-picker--mobile")).toBe(true);
    expect(popup.style.position).toBe("fixed");
    expect(popup.style.left).toBe("8px");
    expect(popup.style.right).toBe("8px");
    expect(popup.style.bottom).toBe("8px");
    expect(popup.style.width).toBe("auto");
  });

  it("reads the time row like a clock: hour left, minute right, label right", async () => {
    const doc = await mount(
      '<div class="form-row"><input id="id_date" data-jalali-date="true" data-jalali-with-time="true" value="۱۴۰۵/۰۷/۲۷ ۱۰:۳۰"></div>'
    );
    doc.querySelector(".jalali-date-open").click();

    const timeRow = doc.querySelector(".jalali-date-picker__time");
    expect(timeRow).toBeTruthy();
    // The row itself is LTR, so the DOM order IS the visual order...
    expect(timeRow.getAttribute("dir")).toBe("ltr");
    // ... hour, then the separator, then the minute.
    const order = [...timeRow.children].map((node) =>
      node.classList.contains("jalali-date-picker__time-select")
        ? node.getAttribute("aria-label")
        : node.className || node.textContent
    );
    expect(order).toEqual([
      "ساعت",
      "jalali-date-picker__time-sep",
      "دقیقه",
      "jalali-date-picker__confirm",
      "jalali-date-picker__time-label",
    ]);
    // The «زمان:» label is the LAST child -- the right edge of an LTR row.
    expect(timeRow.lastElementChild.textContent).toBe("زمان:");
    expect(timeRow.lastElementChild.className).toBe("jalali-date-picker__time-label");

    // The stored value still round-trips through the selects.
    const selects = timeRow.querySelectorAll(".jalali-date-picker__time-select");
    expect(selects[0].value).toBe("10");
    expect(selects[1].value).toBe("30");
  });

  it("initializes inline rows cloned from the decorated empty form", async () => {
    const doc = await mount(
      '<div class="empty-form" id="empty"><input id="id_empty_date" data-jalali-date="true"></div><div id="inline-group"></div>',
    );
    const row = doc.getElementById("empty").cloneNode(true);
    row.id = "added-inline-row";
    doc.getElementById("inline-group").appendChild(row);
    await new Promise((resolve) => setTimeout(resolve, 0));

    const button = row.querySelector(".jalali-date-open");
    expect(button).not.toBeNull();
    expect(row.querySelectorAll(".jalali-date-wrap")).toHaveLength(1);
    button.click();
    expect(doc.getElementById(button.getAttribute("aria-controls")).hidden).toBe(false);
  });
});
