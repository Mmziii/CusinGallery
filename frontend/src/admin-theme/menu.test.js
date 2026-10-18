/**
 * Shared admin menu/popover contract, executed against the shipped theme.js.
 * Covers pointer and keyboard open/close, focus restoration, outside-click,
 * arrow navigation and the real Django changelist action POST fields.
 */
import { afterEach, describe, expect, it } from "vitest";
import { mountAdminPage, readAdminScript } from "../test/adminFrame";

const MENU = `
<button type="button" id="outside">بیرون</button>
<div class="cusin-menu" data-cusin-menu>
  <button type="button" id="menu-trigger" data-cusin-menu-trigger aria-controls="menu-panel">منو</button>
  <div id="menu-panel" data-cusin-menu-panel role="menu" hidden>
    <button type="button" role="menuitem" id="menu-first">گزینهٔ نخست</button>
    <button type="button" role="menuitem" id="menu-second">گزینهٔ دوم</button>
  </div>
</div>`;

const SIDEBAR = `
<div id="cusin-drawer">
  <div class="cusin-nav-groups">
    <details data-cusin-nav-group="catalog" open>
      <summary aria-expanded="true">فهرست کالاها</summary>
      <ul><li><a href="/admin/products/product/">کالاها</a></li></ul>
    </details>
  </div>
</div>`;

const BULK_FORM = `
<div id="changelist">
  <div class="changelist-form-container">
    <form id="changelist-form" method="post">
      <div class="actions">
        <label>اقدام
          <select name="action">
            <option value="">---------</option>
            <option value="publish_items">انتشار موارد</option>
            <option value="delete_selected">حذف موارد انتخاب‌شده</option>
          </select>
        </label>
        <button type="submit" name="index" value="0">برو</button>
        <span class="action-counter">۱ مورد انتخاب شده</span>
      </div>
      <input type="hidden" name="csrfmiddlewaretoken" value="test-csrf">
      <input type="checkbox" name="_selected_action" value="42" checked>
    </form>
  </div>
</div>`;

let mounted;
afterEach(() => {
  if (mounted) mounted.cleanup();
  mounted = null;
});

function mount(html) {
  mounted = mountAdminPage(html, [readAdminScript("theme.js")]);
  const { doc, win } = mounted;
  const key = (target, value) => {
    const event = new win.KeyboardEvent("keydown", { key: value, bubbles: true, cancelable: true });
    target.dispatchEvent(event);
    return event;
  };
  return { doc, win, key };
}

describe("shared menu behavior", () => {
  it("opens by click, exposes ARIA state, and focuses the first item", () => {
    const { doc } = mount(MENU);
    const trigger = doc.getElementById("menu-trigger");
    const panel = doc.getElementById("menu-panel");
    expect(panel.hidden).toBe(true);
    trigger.click();
    expect(panel.hidden).toBe(false);
    expect(trigger.getAttribute("aria-haspopup")).toBe("menu");
    expect(trigger.getAttribute("aria-expanded")).toBe("true");
    expect(doc.activeElement).toBe(doc.getElementById("menu-first"));
  });

  it.each(["Enter", " "])('opens from the trigger with %s', (keyName) => {
    const { doc, key } = mount(MENU);
    const trigger = doc.getElementById("menu-trigger");
    trigger.focus();
    const event = key(trigger, keyName);
    expect(event.defaultPrevented).toBe(true);
    expect(doc.getElementById("menu-panel").hidden).toBe(false);
    expect(doc.activeElement.id).toBe("menu-first");
  });

  it("moves with ArrowUp and ArrowDown and wraps at the edge", () => {
    const { doc, key } = mount(MENU);
    doc.getElementById("menu-trigger").click();
    const first = doc.getElementById("menu-first");
    const second = doc.getElementById("menu-second");
    key(first, "ArrowDown");
    expect(doc.activeElement).toBe(second);
    key(second, "ArrowDown");
    expect(doc.activeElement).toBe(first);
    key(first, "ArrowUp");
    expect(doc.activeElement).toBe(second);
  });

  it("closes on Escape and returns focus to the trigger", () => {
    const { doc, key } = mount(MENU);
    const trigger = doc.getElementById("menu-trigger");
    trigger.click();
    const event = key(doc.getElementById("menu-first"), "Escape");
    expect(event.defaultPrevented).toBe(true);
    expect(doc.getElementById("menu-panel").hidden).toBe(true);
    expect(trigger.getAttribute("aria-expanded")).toBe("false");
    expect(doc.activeElement).toBe(trigger);
  });

  it("closes on outside click without stealing focus from the clicked control", () => {
    const { doc } = mount(MENU);
    doc.getElementById("menu-trigger").click();
    const outside = doc.getElementById("outside");
    outside.focus();
    outside.click();
    expect(doc.getElementById("menu-panel").hidden).toBe(true);
    expect(doc.activeElement).toBe(outside);
  });
});

describe("per-user sidebar group persistence", () => {
  it("restores and saves the group state under the current user key", async () => {
    mounted = mountAdminPage(SIDEBAR, []);
    const { doc, win } = mounted;
    const values = new Map([["cusin-admin-nav:v2:41", JSON.stringify({ groups: { catalog: false } })]]);
    const reads = [];
    const writes = [];
    Object.defineProperty(win, "sessionStorage", {
      configurable: true,
      value: {
        getItem(key) { reads.push(key); return values.get(key) || null; },
        setItem(key, value) { writes.push(key); values.set(key, value); },
      },
    });
    doc.body.setAttribute("data-cusin-user-id", "41");
    win.eval(readAdminScript("theme.js"));
    doc.dispatchEvent(new win.Event("DOMContentLoaded"));

    const group = doc.querySelector("[data-cusin-nav-group]");
    const summary = group.querySelector("summary");
    expect(group.open).toBe(false);
    expect(summary.getAttribute("aria-expanded")).toBe("false");
    summary.click();
    await new Promise((resolve) => win.setTimeout(resolve, 0));
    expect(group.open).toBe(true);
    expect(summary.getAttribute("aria-expanded")).toBe("true");
    expect(reads).toContain("cusin-admin-nav:v2:41");
    expect(writes).toContain("cusin-admin-nav:v2:41");
    expect(JSON.parse(values.get("cusin-admin-nav:v2:41")).groups.catalog).toBe(true);
  });

  it("keeps native disclosure usable when browser storage throws", async () => {
    mounted = mountAdminPage(SIDEBAR, []);
    const { doc, win } = mounted;
    Object.defineProperty(win, "sessionStorage", {
      configurable: true,
      value: {
        getItem() { throw new win.DOMException("blocked", "SecurityError"); },
        setItem() { throw new win.DOMException("blocked", "SecurityError"); },
      },
    });
    doc.body.setAttribute("data-cusin-user-id", "42");
    win.eval(readAdminScript("theme.js"));
    doc.dispatchEvent(new win.Event("DOMContentLoaded"));
    const group = doc.querySelector("[data-cusin-nav-group]");
    group.querySelector("summary").click();
    await new Promise((resolve) => win.setTimeout(resolve, 0));
    expect(group.open).toBe(false);
    expect(group.querySelector("summary").getAttribute("aria-expanded")).toBe("false");
  });
});

describe("Django bulk action menu contract", () => {
  it("posts the selected action, selected ids, CSRF field and index=0", () => {
    const { doc, win } = mount(BULK_FORM);
    const form = doc.getElementById("changelist-form");
    const submitted = [];
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      const values = new win.FormData(form);
      submitted.push({
        action: values.get("action"),
        selected: values.getAll("_selected_action"),
        csrf: values.get("csrfmiddlewaretoken"),
        index: event.submitter && event.submitter.value,
        submitterName: event.submitter && event.submitter.name,
      });
    });

    const trigger = doc.querySelector(".cusin-bulk-menu [data-cusin-menu-trigger]");
    expect(trigger).not.toBeNull();
    trigger.click();
    doc.querySelector('[data-cusin-action-value="publish_items"]').click();

    expect(submitted).toEqual([{
      action: "publish_items",
      selected: ["42"],
      csrf: "test-csrf",
      index: "0",
      submitterName: "index",
    }]);
    expect(doc.querySelector(".cusin-bulk-menu [data-cusin-menu-panel]").hidden).toBe(true);
  });

  it("requires a confirmation step before submitting a destructive action", () => {
    const { doc, win } = mount(BULK_FORM);
    const form = doc.getElementById("changelist-form");
    const submitted = [];
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      submitted.push({
        action: new win.FormData(form).get("action"),
        selected: new win.FormData(form).getAll("_selected_action"),
        index: event.submitter && event.submitter.value,
      });
    });

    doc.querySelector(".cusin-bulk-menu [data-cusin-menu-trigger]").click();
    doc.querySelector('[data-cusin-action-value="delete_selected"]').click();
    expect(submitted).toHaveLength(0);
    expect(doc.querySelector(".cusin-menu-confirm-message").textContent).toContain("مطمئن هستید");
    doc.querySelector("[data-cusin-confirm-yes]").click();
    expect(submitted).toEqual([{ action: "delete_selected", selected: ["42"], index: "0" }]);
  });
});
