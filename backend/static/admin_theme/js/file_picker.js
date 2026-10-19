/* کازین گالری — انتخاب‌گر فایل فارسی برای پنل مدیریت.
 *
 * مرورگر متن دکمهٔ <input type="file"> را با زبان خودش نشان می‌دهد
 * («Choose File / No file chosen»)، که در پنل فارسی جا نمی‌افتد. این اسکریپت
 * ورودی را پنهان می‌کند و به جایش یک دکمهٔ «انتخاب فایل»، نام فایلِ
 * انتخاب‌شده و تصویر بندانگشتیِ فایل فعلی می‌گذارد؛ خود input دست‌نخورده
 * می‌ماند، پس فرم همان‌طور که انتظار داریم ارسال می‌شود.
 *
 * رویدادها به‌صورت delegation روی document شنیده می‌شوند تا ردیف‌هایی که
 * Django بعداً از «empty form» اینلاین‌ها می‌سازد (تصاویر محصول) هم بدون
 * شنوندهٔ جداگانه کار کنند.
 */
(function () {
  "use strict";

  var CHOOSE_LABEL = "انتخاب فایل";
  var EMPTY_LABEL = "فایلی انتخاب نشده";

  function pickerOf(node) {
    return node && node.closest ? node.closest(".cusin-file-picker") : null;
  }

  function fileInputOf(picker) {
    return picker ? picker.querySelector(".cusin-file-picker__input") : null;
  }

  /** The file already saved for this field (the stock «در حال حاضر» link). */
  function currentFileLink(picker) {
    var box = picker && picker.parentElement;
    if (!box) return null;
    var link = box.querySelector("a[href]");
    if (!link) return null;
    var href = link.getAttribute("href") || "";
    return href && href.charAt(0) !== "#" ? link : null;
  }

  function showCurrent(picker) {
    var thumb = picker.querySelector("[data-cusin-file-picker-thumb]");
    var name = picker.querySelector(".cusin-file-picker__name");
    var link = currentFileLink(picker);
    if (!thumb || !name) return;
    if (link) {
      thumb.src = link.getAttribute("href");
      thumb.hidden = false;
      name.textContent = (link.textContent || "").trim() || EMPTY_LABEL;
    } else {
      thumb.hidden = true;
      thumb.removeAttribute("src");
      name.textContent = EMPTY_LABEL;
    }
  }

  function showChosen(picker, file) {
    var thumb = picker.querySelector("[data-cusin-file-picker-thumb]");
    var name = picker.querySelector(".cusin-file-picker__name");
    if (!name) return;
    if (!file) {
      showCurrent(picker);
      return;
    }
    name.textContent = file.name || EMPTY_LABEL;
    if (!thumb) return;
    if (
      file.type &&
      file.type.indexOf("image/") === 0 &&
      typeof window.URL !== "undefined" &&
      typeof window.URL.createObjectURL === "function"
    ) {
      thumb.src = window.URL.createObjectURL(file);
      thumb.hidden = false;
    }
  }

  function isUsableInput(input) {
    if (input.type !== "file" || input.multiple) return false;
    if (input.dataset.cusinFilePicker === "1") return false;
    var style = window.getComputedStyle ? window.getComputedStyle(input) : null;
    return !style || style.display !== "none";
  }

  function build(input) {
    input.dataset.cusinFilePicker = "1";
    input.classList.add("cusin-file-picker__input");
    input.setAttribute("aria-label", CHOOSE_LABEL);

    var wrapper = document.createElement("div");
    wrapper.className = "cusin-file-picker";

    var thumbnail = document.createElement("img");
    thumbnail.className = "cusin-file-picker__thumb";
    thumbnail.setAttribute("data-cusin-file-picker-thumb", "1");
    thumbnail.alt = "";
    thumbnail.hidden = true;

    var button = document.createElement("button");
    button.type = "button";
    button.className = "button cusin-file-picker__button";
    button.textContent = CHOOSE_LABEL;

    var name = document.createElement("span");
    name.className = "cusin-file-picker__name";
    name.textContent = EMPTY_LABEL;

    input.parentNode.insertBefore(wrapper, input);
    wrapper.appendChild(thumbnail);
    wrapper.appendChild(input);
    wrapper.appendChild(button);
    wrapper.appendChild(name);

    // Thumbnail of the saved file (the link is the stock «در حال حاضر» one).
    var existing = currentFileLink(wrapper);
    if (existing) {
      thumbnail.src = existing.getAttribute("href");
      thumbnail.hidden = false;
      name.textContent = (existing.textContent || "").trim() || EMPTY_LABEL;
      thumbnail.addEventListener("error", function () {
        thumbnail.hidden = true;
      });
    }
    return wrapper;
  }

  function init() {
    var inputs = document.querySelectorAll('input[type="file"]');
    Array.prototype.forEach.call(inputs, function (input) {
      if (isUsableInput(input)) build(input);
    });
  }

  /* Delegated so cloned inline rows keep working. */
  document.addEventListener("click", function (event) {
    var button = event.target.closest && event.target.closest(".cusin-file-picker__button");
    if (!button) return;
    var input = fileInputOf(pickerOf(button));
    if (input) input.click();
  });

  document.addEventListener("change", function (event) {
    var target = event.target;
    if (!target) return;
    if (
      target.classList &&
      target.classList.contains("cusin-file-picker__input")
    ) {
      var picker = pickerOf(target);
      if (picker) showChosen(picker, target.files && target.files[0]);
      return;
    }
    // Stock clear checkbox: the saved file disappears with the thumbnail.
    if (
      target.type === "checkbox" &&
      /-clear$/.test(target.name || "") &&
      target.parentElement
    ) {
      var sibling = target.parentElement.querySelector(".cusin-file-picker");
      if (!sibling) return;
      if (target.checked) {
        var thumb = sibling.querySelector("[data-cusin-file-picker-thumb]");
        var name = sibling.querySelector(".cusin-file-picker__name");
        if (thumb) {
          thumb.hidden = true;
          thumb.removeAttribute("src");
        }
        if (name) name.textContent = EMPTY_LABEL;
      } else {
        showCurrent(sibling);
      }
    }
  });

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      setTimeout(init, 0);
    });
  } else {
    setTimeout(init, 0);
  }
})();
