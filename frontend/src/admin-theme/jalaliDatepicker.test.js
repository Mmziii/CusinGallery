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

describe("Jalali date picker", () => {
  it("initializes on DOMContentLoaded, opens, and writes selected Persian digits", async () => {
    const doc = await mount();
    const input = doc.getElementById("id_date");
    const button = doc.querySelector(".jalali-date-open");
    const popup = doc.querySelector(".jalali-date-picker");

    expect(button).not.toBeNull();
    button.click();
    expect(popup.hidden).toBe(false);

    popup.querySelector('[aria-label="۱۴۰۵/۰۷/۰۱"]').click();
    expect(input.value).toBe("۱۴۰۵/۰۷/۰۱");
    expect(popup.hidden).toBe(true);
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
    expect(row.querySelector(".jalali-date-picker").hidden).toBe(false);
  });
});
