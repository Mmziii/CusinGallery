/**
 * The Persian file picker (admin_theme/js/file_picker.js).
 *
 * Browsers render the native file control in their own UI language
 * («Choose File / No file chosen»), which cannot be changed from the page.
 * The script hides the native control and renders a Persian button, the
 * chosen file name and a thumbnail of the current image, while leaving the
 * real <input type="file"> in the form so the upload is unchanged.
 */
import { afterEach, describe, expect, it } from "vitest";

import { mountAdminPage, readAdminScript } from "../test/adminFrame";

const FIELD_HTML = `
<fieldset class="module aligned">
  <div class="form-row field-logo_light">
    <div>
      <div class="flex-container">
        <label for="id_logo_light">لوگوی هدر روشن:</label>
        <div>
          در حال حاضر: <a href="/media/brand/logo-light.png">brand/logo-light.png</a>
          <input type="checkbox" name="logo_light-clear" id="logo_light-clear_id">
          <label for="logo_light-clear_id">پاک کردن</label><br>
          تغییر: <input type="file" name="logo_light" accept="image/*" id="id_logo_light">
        </div>
      </div>
    </div>
  </div>
</fieldset>
`;

let mounted = null;

async function mount() {
  mounted = mountAdminPage(FIELD_HTML, [readAdminScript("file_picker.js")]);
  // init() is deferred by one macrotask so every stock widget is mounted.
  await new Promise((resolve) => setTimeout(resolve, 20));
  return mounted.doc;
}

function chooseFile(win, input, file) {
  Object.defineProperty(input, "files", {
    configurable: true,
    value: [file],
  });
  input.dispatchEvent(new win.Event("change", { bubbles: true }));
}

afterEach(() => {
  if (mounted) mounted.cleanup();
  mounted = null;
});

describe("Persian file picker", () => {
  it("replaces the browser UI with Persian labels and keeps the real input", async () => {
    const doc = await mount();
    const input = doc.getElementById("id_logo_light");

    const picker = doc.querySelector(".cusin-file-picker");
    expect(picker).not.toBeNull();
    // The input stays inside the form with the name the view expects.
    expect(picker.contains(input)).toBe(true);
    expect(input.getAttribute("name")).toBe("logo_light");

    const button = picker.querySelector(".cusin-file-picker__button");
    expect(button.textContent).toBe("انتخاب فایل");

    const name = picker.querySelector(".cusin-file-picker__name");
    expect(name.textContent).toBe("brand/logo-light.png");
  });

  it("shows a thumbnail of the current image", async () => {
    const doc = await mount();
    const thumb = doc.querySelector(".cusin-file-picker__thumb");
    expect(thumb).not.toBeNull();
    expect(thumb.hidden).toBe(false);
    expect(thumb.getAttribute("src")).toBe("/media/brand/logo-light.png");
    expect(thumb.getAttribute("alt")).toBe("");
  });

  it("shows the chosen file's name (and preview) before submitting", async () => {
    const doc = await mount();
    const win = mounted.win;
    win.URL.createObjectURL = () => "blob:new-logo";
    const input = doc.getElementById("id_logo_light");

    chooseFile(win, input, { name: "logo-new.png", type: "image/png" });

    const picker = doc.querySelector(".cusin-file-picker");
    expect(picker.querySelector(".cusin-file-picker__name").textContent).toBe(
      "logo-new.png",
    );
    const thumb = picker.querySelector(".cusin-file-picker__thumb");
    expect(thumb.hidden).toBe(false);
    expect(thumb.src).toBe("blob:new-logo");
  });

  it("opens the file dialog from the Persian button", async () => {
    const doc = await mount();
    const picker = doc.querySelector(".cusin-file-picker");
    const input = picker.querySelector(".cusin-file-picker__input");
    let opened = 0;
    input.addEventListener("click", () => {
      opened += 1;
    });

    picker.querySelector(".cusin-file-picker__button").click();

    expect(opened).toBe(1);
  });

  it("keeps working for inline rows cloned from the empty form", async () => {
    const doc = await mount();
    const row = doc.querySelector(".form-row");
    // Django's inlines.js clones the hidden empty form; listeners are not
    // cloned with nodes, so only the delegated handlers can make the copy work.
    const clone = row.cloneNode(true);
    clone.querySelector("input[type=\"file\"]").setAttribute("name", "logo_dark");
    doc.querySelector("fieldset").appendChild(clone);

    const picker = clone.querySelector(".cusin-file-picker");
    const input = picker.querySelector(".cusin-file-picker__input");
    let opened = 0;
    input.addEventListener("click", () => {
      opened += 1;
    });
    picker.querySelector(".cusin-file-picker__button").click();
    expect(opened).toBe(1);

    Object.defineProperty(input, "files", {
      configurable: true,
      value: [{ name: "clone.png", type: "image/png" }],
    });
    input.dispatchEvent(new mounted.win.Event("change", { bubbles: true }));
    expect(picker.querySelector(".cusin-file-picker__name").textContent).toBe(
      "clone.png",
    );
  });

  it("falls back to the Persian empty label and hides the thumbnail on clear", async () => {
    const doc = await mount();
    const clear = doc.getElementById("logo_light-clear_id");

    clear.checked = true;
    clear.dispatchEvent(new doc.defaultView.Event("change", { bubbles: true }));

    const picker = doc.querySelector(".cusin-file-picker");
    expect(picker.querySelector(".cusin-file-picker__name").textContent).toBe(
      "فایلی انتخاب نشده",
    );
    expect(picker.querySelector(".cusin-file-picker__thumb").hidden).toBe(true);
  });
});
