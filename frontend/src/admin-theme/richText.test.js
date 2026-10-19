/**
 * «صفحات اطلاعاتی» rich-text toolbar: a plain textarea plus buttons that
 * insert the SAME markup the backend allowlist accepts.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { mountAdminPage, readAdminScript } from "../test/adminFrame";

const FORM = `
<form>
  <div class="form-row">
    <textarea name="body" data-cusin-rich-text="1" rows="6">متن اولیه</textarea>
  </div>
</form>`;

let mounted;
afterEach(() => {
  if (mounted) mounted.cleanup();
  mounted = null;
  vi.restoreAllMocks();
});

async function mount() {
  mounted = mountAdminPage(FORM, [readAdminScript("rich_text.js")]);
  await new Promise((resolve) => setTimeout(resolve, 20));
  return mounted;
}

function textarea(doc) {
  return doc.querySelector('textarea[name="body"]');
}

function selectAll(doc) {
  const field = textarea(doc);
  field.focus();
  field.setSelectionRange(0, field.value.length);
  return field;
}

describe("rich-text toolbar", () => {
  it("adds one labeled toolbar above the textarea", async () => {
    const { doc } = await mount();
    const toolbar = doc.querySelector(".cusin-rich-text-toolbar");
    expect(toolbar).not.toBeNull();
    expect(toolbar.getAttribute("role")).toBe("toolbar");
    expect(toolbar.querySelectorAll("button")).toHaveLength(5);
    expect(toolbar.querySelector('[data-cusin-format="bold"]').textContent).toBe("ب");
    expect(toolbar.querySelector('[data-cusin-format="bold"]').getAttribute("aria-label")).toBe("پررنگ");
    // It is inserted before the textarea, not after it.
    expect(toolbar.nextElementSibling).toBe(textarea(doc));
  });

  it("wraps the selection in strong / em / h2 / list markup", async () => {
    const { doc } = await mount();
    selectAll(doc);
    doc.querySelector('[data-cusin-format="bold"]').click();
    expect(textarea(doc).value).toBe("<strong>متن اولیه</strong>");

    selectAll(doc);
    doc.querySelector('[data-cusin-format="italic"]').click();
    expect(textarea(doc).value).toBe("<em><strong>متن اولیه</strong></em>");

    selectAll(doc);
    doc.querySelector('[data-cusin-format="heading"]').click();
    expect(textarea(doc).value.startsWith("<h2>")).toBe(true);

    textarea(doc).value = "متن اولیه";
    selectAll(doc);
    doc.querySelector('[data-cusin-format="list"]').click();
    expect(textarea(doc).value).toContain("<ul>");
    expect(textarea(doc).value).toContain("<li>متن اولیه</li>");
  });

  it("inserts a safe link only", async () => {
    const { doc, win } = await mount();
    const alertSpy = vi.fn();
    win.alert = alertSpy;
    win.prompt = vi.fn(() => "javascript:alert(1)");
    selectAll(doc);
    doc.querySelector('[data-cusin-format="link"]').click();
    expect(alertSpy).toHaveBeenCalled();
    expect(textarea(doc).value).toBe("متن اولیه");

    win.prompt = vi.fn(() => "https://cusin.ir/about/");
    doc.querySelector('[data-cusin-format="link"]').click();
    expect(textarea(doc).value).toBe(
      '<a href="https://cusin.ir/about/">متن اولیه</a>'
    );
  });

  it("dispatches an input event so the admin's unsaved-changes guard sees edits", async () => {
    const { doc, win } = await mount();
    const onInput = vi.fn();
    textarea(doc).addEventListener("input", onInput);
    selectAll(doc);
    doc.querySelector('[data-cusin-format="bold"]').click();
    expect(onInput).toHaveBeenCalled();
    expect(win.Event).toBeTypeOf("function");
  });
});
