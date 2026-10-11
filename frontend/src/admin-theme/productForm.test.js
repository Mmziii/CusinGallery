/**
 * B4d: the product change form's progressive enhancements, executed for real.
 *
 * The scripts under test are the shipped files in backend/static/admin_theme/js
 * (not copies). They run in an isolated jsdom iframe against markup that uses
 * the same ids, classes and data-attributes the Django template renders; the
 * backend suite asserts those hooks exist on the real page
 * (apps/adminui/tests/test_admin_js_contract.py), so the fixture cannot drift.
 */
import { afterEach, describe, expect, it } from "vitest";
import { mountAdminPage, readAdminScript } from "../test/adminFrame";

const FORM_HTML = `
<div id="content-main">
<form method="post" action="">
  <fieldset class="module" id="g-main"><h2>اطلاعات اصلی</h2>
    <input type="text" id="id_name" name="name" value="">
    <input type="text" id="id_slug" name="slug" value="">
    <input type="number" id="id_price" name="price" value="1234567">
    <input type="number" id="id_compare_at_price" name="compare_at_price" value="">
    <input type="number" id="id_discount_percentage" name="discount_percentage" value="0">
    <input type="number" id="id_stock_quantity" name="stock_quantity" value="5">
    <input type="number" id="id_low_stock_threshold" name="low_stock_threshold" value="3">
    <textarea id="id_short_description" name="short_description"></textarea>
    <textarea id="id_description" name="description">سه</textarea>
  </fieldset>
  <fieldset class="module" id="g-images"><h2>تصاویر</h2>
    <div class="js-inline-admin-formset">
      <img src="/media/products/main.png" alt="">
      <input type="file" name="images-0-image">
    </div>
  </fieldset>
  <div class="submit-row"><input type="submit" name="_save" class="default" value="ذخیره"></div>
</form>
</div>
<nav data-cusin-anchor-nav></nav>
<div data-cusin-preview>
  <span data-cusin-preview-name>نام محصول</span>
  <span data-cusin-preview-price>—</span>
  <span data-cusin-preview-compare hidden></span>
  <div data-cusin-preview-image></div>
</div>
`;

const SCRIPTS = () => [readAdminScript("product_form.js")];

let mounted = null;
function mount(html = FORM_HTML) {
  mounted = mountAdminPage(html, SCRIPTS());
  const { doc } = mounted;
  return {
    doc,
    win: mounted.win,
    input: (id) => doc.getElementById(id),
    form: () => doc.querySelector("#content-main form"),
  };
}

function typeInto(win, input, value) {
  input.value = value;
  input.dispatchEvent(new win.Event("input", { bubbles: true }));
}

afterEach(() => {
  if (mounted) mounted.cleanup();
  mounted = null;
});

describe("anchored section bar", () => {
  it("builds one link per fieldset, labelled by its heading", () => {
    const { doc } = mount();
    const links = [...doc.querySelectorAll("[data-cusin-anchor-nav] a")];
    expect(links.map((a) => a.textContent)).toEqual(["اطلاعات اصلی", "تصاویر"]);
    expect(links[0].getAttribute("href")).toBe("#g-main");
  });

  it("scrolls to the section and marks only that link active", () => {
    const { doc, win } = mount();
    const [first, second] = [...doc.querySelectorAll("[data-cusin-anchor-nav] a")];
    second.dispatchEvent(new win.MouseEvent("click", { bubbles: true, cancelable: true }));
    expect(win.__scrolled.map((el) => el.id)).toContain("g-images");
    expect(second.classList.contains("is-active")).toBe(true);
    expect(first.classList.contains("is-active")).toBe(false);
  });

  it("removes the bar when the form has no sections", () => {
    const { doc } = mount(`
      <div id="content-main"><form>
        <input id="id_name"><input id="id_price">
        <input type="submit" class="default">
      </form></div>
      <nav data-cusin-anchor-nav></nav>`);
    expect(doc.querySelector("[data-cusin-anchor-nav]")).toBeNull();
  });
});

describe("numeric inputs: separators, Persian digits, plain submit", () => {
  it("switches to a text input with a numeric keyboard and keeps plain digits", () => {
    const { input } = mount();
    const price = input("id_price");
    expect(price.type).toBe("text");
    expect(price.getAttribute("inputmode")).toBe("numeric");
    expect(price.value).toBe("1234567");
  });

  it("normalizes Persian and Arabic digits to ASCII while typing", () => {
    const { input, win } = mount();
    const price = input("id_price");
    typeInto(win, price, "۱۲۳۴۵");
    expect(price.value).toBe("12345");
    typeInto(win, price, "٠١٢");
    expect(price.value).toBe("012");
  });

  it("strips separators typed by hand", () => {
    const { input, win } = mount();
    const price = input("id_price");
    typeInto(win, price, "1,234");
    expect(price.value).toBe("1234");
  });

  it("groups thousands with the Arabic separator on blur and ungroups on focus", () => {
    const { input, win } = mount();
    const price = input("id_price");
    price.value = "1234567";
    price.dispatchEvent(new win.Event("blur"));
    expect(price.value).toBe("۱٬۲۳۴٬۵۶۷");
    price.dispatchEvent(new win.Event("focus"));
    expect(price.value).toBe("1234567");
  });

  it("submits plain ASCII digits even when the field shows separators", () => {
    const { input, win, form } = mount();
    const price = input("id_price");
    price.value = "۱٬۲۳۴";
    const submitted = [];
    form().addEventListener("submit", (event) => {
      event.preventDefault();
      submitted.push(new win.FormData(form()).get("price"));
    });
    form().dispatchEvent(new win.Event("submit", { cancelable: true }));
    expect(submitted).toEqual(["1234"]);
    expect(price.value).toBe("1234");
  });

  it("leaves an empty numeric field empty", () => {
    const { input, win } = mount();
    const compare = input("id_compare_at_price");
    compare.dispatchEvent(new win.Event("blur"));
    expect(compare.value).toBe("");
  });
});

describe("live storefront preview card", () => {
  it("shows the name, falling back to the placeholder when empty", () => {
    const { input, doc, win } = mount();
    const name = doc.querySelector("[data-cusin-preview-name]");
    typeInto(win, input("id_name"), "کتری لعابی");
    expect(name.textContent).toBe("کتری لعابی");
    typeInto(win, input("id_name"), "   ");
    expect(name.textContent).toBe("نام محصول");
  });

  it("formats the price with Persian digits, separators and the toman unit", () => {
    const { input, doc, win } = mount();
    const price = doc.querySelector("[data-cusin-preview-price]");
    typeInto(win, input("id_price"), "1234567");
    expect(price.textContent).toBe("۱٬۲۳۴٬۵۶۷ تومان");
    typeInto(win, input("id_price"), "");
    expect(price.textContent).toBe("—");
  });

  it("shows the compare-at price only when it is set", () => {
    const { input, doc, win } = mount();
    const compare = doc.querySelector("[data-cusin-preview-compare]");
    expect(compare.hidden).toBe(true);
    typeInto(win, input("id_compare_at_price"), "2000000");
    expect(compare.hidden).toBe(false);
    expect(compare.textContent).toBe("۲٬۰۰۰٬۰۰۰ تومان");
    typeInto(win, input("id_compare_at_price"), "");
    expect(compare.hidden).toBe(true);
  });

  it("reuses the first existing image from the images inline", () => {
    const { doc } = mount();
    const img = doc.querySelector("[data-cusin-preview-image] img");
    expect(img).not.toBeNull();
    // img.src is the resolved absolute URL, as in a browser
    expect(img.src.endsWith("/media/products/main.png")).toBe(true);
  });

  it("falls back to the placeholder icon when there is no image", () => {
    const { doc } = mount(FORM_HTML.replace('<img src="/media/products/main.png" alt="">', ""));
    expect(doc.querySelector("[data-cusin-preview-image] img")).toBeNull();
    expect(
      doc.querySelector('[data-cusin-preview-image] use[href="#cusin-i-image-off"]')
    ).not.toBeNull();
  });
});

describe("SEO character counters", () => {
  it("counts characters with Persian digits next to each field", () => {
    const { input, doc, win } = mount();
    const name = input("id_name");
    expect(name.nextElementSibling.classList.contains("cusin-counter")).toBe(true);
    typeInto(win, name, "کتری");
    expect(name.nextElementSibling.textContent).toBe("۴ / ۲۵۵ نویسه");
    expect(doc.querySelectorAll(".cusin-counter").length).toBe(4);
  });

  it("marks the counter as over the limit past the maximum", () => {
    const { input, win } = mount();
    const name = input("id_name");
    typeInto(win, name, "ا".repeat(255));
    expect(name.nextElementSibling.classList.contains("is-over")).toBe(false);
    typeInto(win, name, "ا".repeat(256));
    expect(name.nextElementSibling.classList.contains("is-over")).toBe(true);
    expect(name.nextElementSibling.textContent).toBe("۲۵۶ / ۲۵۵ نویسه");
  });

  it("shows a plain count for fields without a limit", () => {
    const { input } = mount();
    // the description fixture holds «سه» (2 characters)
    expect(input("id_description").nextElementSibling.textContent).toBe("۲ نویسه");
  });
});

describe("unsaved-changes warning", () => {
  function beforeUnloadPrevented(win) {
    const event = new win.Event("beforeunload", { cancelable: true });
    win.dispatchEvent(event);
    return event.defaultPrevented;
  }

  it("does not warn on a clean form", () => {
    const { win } = mount();
    expect(beforeUnloadPrevented(win)).toBe(false);
  });

  it("warns after an edit", () => {
    const { input, win } = mount();
    typeInto(win, input("id_name"), "تغییر");
    expect(beforeUnloadPrevented(win)).toBe(true);
  });

  it("stops warning once the form is submitted", () => {
    const { input, win, form } = mount();
    typeInto(win, input("id_name"), "تغییر");
    form().addEventListener("submit", (event) => event.preventDefault());
    form().dispatchEvent(new win.Event("submit", { cancelable: true }));
    expect(beforeUnloadPrevented(win)).toBe(false);
  });
});

describe("Ctrl+S submits the form", () => {
  function pressKey(win, doc, init) {
    const event = new win.KeyboardEvent("keydown", { bubbles: true, cancelable: true, ...init });
    doc.body.dispatchEvent(event);
    return event;
  }

  it("clicks the default save button and cancels the browser save dialog", () => {
    const { win, doc } = mount();
    const save = doc.querySelector('input[type="submit"].default');
    let clicks = 0;
    save.addEventListener("click", (event) => {
      clicks += 1;
      event.preventDefault(); // keep jsdom from navigating
    });
    const event = pressKey(win, doc, { key: "s", ctrlKey: true });
    expect(clicks).toBe(1);
    expect(event.defaultPrevented).toBe(true);
  });

  it("also works with Cmd+S on macOS", () => {
    const { win, doc } = mount();
    const save = doc.querySelector('input[type="submit"].default');
    let clicks = 0;
    save.addEventListener("click", (event) => {
      clicks += 1;
      event.preventDefault();
    });
    pressKey(win, doc, { key: "S", metaKey: true });
    expect(clicks).toBe(1);
  });

  it("ignores a plain S key", () => {
    const { win, doc } = mount();
    const save = doc.querySelector('input[type="submit"].default');
    let clicks = 0;
    save.addEventListener("click", (event) => {
      clicks += 1;
      event.preventDefault();
    });
    const event = pressKey(win, doc, { key: "s" });
    expect(clicks).toBe(0);
    expect(event.defaultPrevented).toBe(false);
  });
});

describe("slug", () => {
  it("is not generated by product_form.js (Django's prepopulate.js does it)", () => {
    // Auto-fill is ProductAdmin.prepopulated_fields, rendered by Django. The
    // enhancement script must never write the slug itself, so a manual value
    // always wins. The stock auto-fill behaviour is NOT executed here.
    const { input, win } = mount();
    typeInto(win, input("id_name"), "قابلمه گرانیتی");
    expect(input("id_slug").value).toBe("");
  });
});
