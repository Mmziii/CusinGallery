/* کازین گالری — product change-form enhancements (B4d). Vanilla JS,
 * progressive enhancement only: without it the stock form works exactly
 * as before. Server-side validation is NEVER bypassed -- numeric inputs
 * are normalized back to plain ASCII digits before submit.
 *
 *   1. anchored section bar (built from the real fieldsets)
 *   2. live storefront preview card
 *   3. thousands separators + Persian/Arabic digit normalization
 *   4. SEO character counters
 *   5. unsaved-changes warning + Ctrl+S submit
 */
(function () {
  "use strict";

  var FA_DIGITS = "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩";
  var NUMERIC_IDS = [
    "id_price", "id_compare_at_price", "id_discount_percentage",
    "id_stock_quantity", "id_low_stock_threshold"
  ];
  var COUNTERS = {
    id_name: 255, id_slug: 280, id_short_description: 500, id_description: 0
  };

  function toAsciiDigits(value) {
    return String(value).replace(/[۰-۹٠-٩]/g, function (ch) {
      return String(FA_DIGITS.indexOf(ch) % 10);
    });
  }
  function toFaDigits(value) {
    return String(value).replace(/[0-9]/g, function (d) { return "۰۱۲۳۴۵۶۷۸۹"[Number(d)]; });
  }
  function groupThousands(value) {
    return String(value).replace(/\B(?=(\d{3})+(?!\d))/g, "\u066c");
  }
  function stripFormatting(value) {
    return toAsciiDigits(value).replace(/[^\d]/g, "");
  }

  /* ---------------------------------------------------------------- *
   * 1. Anchored section bar
   * ---------------------------------------------------------------- */
  function initAnchorNav(form) {
    var nav = document.querySelector("[data-cusin-anchor-nav]");
    if (!nav) return;
    var sections = form.querySelectorAll("fieldset.module");
    if (!sections.length) { nav.remove(); return; }

    var links = [];
    sections.forEach(function (section, index) {
      var heading = section.querySelector("h2");
      if (!section.id) section.id = "cusin-section-" + index;
      var label = heading ? heading.textContent.trim() : ("بخش " + (index + 1));
      var link = document.createElement("a");
      link.href = "#" + section.id;
      link.textContent = label;
      link.addEventListener("click", function (event) {
        event.preventDefault();
        section.scrollIntoView({ behavior: "smooth", block: "start" });
        setActive(link);
      });
      nav.appendChild(link);
      links.push({ link: link, section: section });
    });

    function setActive(link) {
      links.forEach(function (item) {
        item.link.classList.toggle("is-active", item.link === link);
      });
    }
    if ("IntersectionObserver" in window) {
      var observer = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) {
            links.forEach(function (item) {
              setActive(item.section === entry.target ? item.link : null);
            });
          }
        });
      }, { rootMargin: "-20% 0px -70% 0px" });
      links.forEach(function (item) { observer.observe(item.section); });
    }
    if (links.length) setActive(links[0].link);
  }

  /* ---------------------------------------------------------------- *
   * 2. Live storefront preview
   * ---------------------------------------------------------------- */
  function initPreview(form) {
    var card = document.querySelector("[data-cusin-preview]");
    if (!card) return;
    var nameEl = card.querySelector("[data-cusin-preview-name]");
    var priceEl = card.querySelector("[data-cusin-preview-price]");
    var compareEl = card.querySelector("[data-cusin-preview-compare]");
    var imageSlot = card.querySelector("[data-cusin-preview-image]");
    var nameInput = form.querySelector("#id_name");
    var priceInput = form.querySelector("#id_price");
    var compareInput = form.querySelector("#id_compare_at_price");

    function money(value) {
      var digits = stripFormatting(value || "");
      if (!digits || Number(digits) === 0) return "";
      return toFaDigits(groupThousands(digits)) + " تومان";
    }
    function refresh() {
      if (nameEl) nameEl.textContent = (nameInput && nameInput.value.trim()) || "نام محصول";
      if (priceEl) priceEl.textContent = money(priceInput && priceInput.value) || "—";
      if (compareEl) {
        var compare = money(compareInput && compareInput.value);
        compareEl.textContent = compare;
        compareEl.hidden = !compare;
      }
    }
    function refreshImage() {
      // Existing primary/current image inside the images inline, else the
      // first newly selected file (FileReader), else the placeholder icon.
      var existing = form.querySelector(".js-inline-admin-formset img[src]");
      var fileInput = form.querySelector('.js-inline-admin-formset input[type="file"]');
      if (existing && existing.src && !existing.src.startsWith("data:text")) {
        imageSlot.innerHTML = "";
        var img = document.createElement("img");
        img.src = existing.src;
        img.alt = "";
        img.className = "cusin-preview-img";
        imageSlot.appendChild(img);
        return;
      }
      if (fileInput && fileInput.files && fileInput.files[0]) {
        var reader = new FileReader();
        reader.onload = function (event) {
          imageSlot.innerHTML = "";
          var img2 = document.createElement("img");
          img2.src = event.target.result;
          img2.alt = "";
          img2.className = "cusin-preview-img";
          imageSlot.appendChild(img2);
        };
        reader.readAsDataURL(fileInput.files[0]);
        return;
      }
      imageSlot.innerHTML =
        '<svg class="cusin-icon" aria-hidden="true"><use href="#cusin-i-image-off"></use></svg>';
    }

    [nameInput, priceInput, compareInput].forEach(function (input) {
      if (input) input.addEventListener("input", refresh);
    });
    form.querySelectorAll('.js-inline-admin-formset input[type="file"]').forEach(function (input) {
      input.addEventListener("change", refreshImage);
    });
    refresh();
    refreshImage();
  }

  /* ---------------------------------------------------------------- *
   * 3. Numeric inputs: Persian digits in, separators on blur
   * ---------------------------------------------------------------- */
  function initNumericInputs(form) {
    NUMERIC_IDS.forEach(function (id) {
      var input = form.querySelector("#" + id);
      if (!input) return;
      // type=number cannot hold separators; switch to text+numeric
      // keyboard. The submitted value stays plain ASCII digits.
      input.setAttribute("inputmode", "numeric");
      input.type = "text";
      input.value = stripFormatting(input.value);

      input.addEventListener("focus", function () {
        input.value = stripFormatting(input.value);
      });
      input.addEventListener("input", function () {
        input.value = stripFormatting(input.value);
      });
      input.addEventListener("blur", function () {
        var digits = stripFormatting(input.value);
        input.value = digits ? toFaDigits(groupThousands(digits)) : "";
      });
    });
    // Never submit formatted text: strip on submit for every numeric id.
    form.addEventListener("submit", function () {
      NUMERIC_IDS.forEach(function (id) {
        var input = form.querySelector("#" + id);
        if (input) input.value = stripFormatting(input.value);
      });
    });
  }

  /* ---------------------------------------------------------------- *
   * 4. Character counters
   * ---------------------------------------------------------------- */
  function initCounters(form) {
    Object.keys(COUNTERS).forEach(function (id) {
      var input = form.querySelector("#" + id);
      if (!input) return;
      var max = COUNTERS[id];
      var counter = document.createElement("div");
      counter.className = "cusin-counter";
      input.insertAdjacentElement("afterend", counter);
      function refresh() {
        var length = input.value.length;
        counter.textContent = max
          ? toFaDigits(length) + " / " + toFaDigits(max) + " نویسه"
          : toFaDigits(length) + " نویسه";
        counter.classList.toggle("is-over", Boolean(max && length > max));
      }
      input.addEventListener("input", refresh);
      refresh();
    });
  }

  /* ---------------------------------------------------------------- *
   * 5. Unsaved-changes warning + Ctrl+S
   * ---------------------------------------------------------------- */
  function initUnsavedGuard(form) {
    var dirty = false;
    form.addEventListener("change", function () { dirty = true; });
    form.addEventListener("input", function () { dirty = true; });
    form.addEventListener("submit", function () { dirty = false; });
    window.addEventListener("beforeunload", function (event) {
      if (!dirty) return undefined;
      event.preventDefault();
      event.returnValue = "";
      return "";
    });
  }

  function initCtrlS(form) {
    document.addEventListener("keydown", function (event) {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") {
        var defaultButton = form.querySelector('input[type="submit"].default') ||
          form.querySelector('input[type="submit"]');
        if (defaultButton) {
          event.preventDefault();
          defaultButton.click();
        }
      }
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    var form = document.querySelector("#content-main form");
    if (!form) return;
    // Only enhance the product change form (the id set is product-specific).
    if (!form.querySelector("#id_price") || !form.querySelector("#id_name")) return;
    initAnchorNav(form);
    initPreview(form);
    initNumericInputs(form);
    initCounters(form);
    initUnsavedGuard(form);
    initCtrlS(form);
  });
})();
