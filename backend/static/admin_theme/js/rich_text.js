/* کازین گالری — نوار ابزار کوچک ویرایشگر متن صفحات اطلاعاتی.
 *
 * عمداً یک textarea با یک نوار ابزار است، نه یک ویرایشگر WYSIWYG سنگین:
 * هیچ وابستگی تازه‌ای اضافه نمی‌کند، با RTL و Vazirmatn کار می‌کند و
 * خروجی همان HTML مجاز است که بک‌اند در sanitize.py تأیید می‌کند
 * (پررنگ، مورب، عنوان، فهرست، پیوند).
 */
(function () {
  "use strict";

  var BUTTONS = [
    { format: "bold", label: "پررنگ", title: "پررنگ (Ctrl+B)", text: "ب" },
    { format: "italic", label: "مورب", title: "مورب (Ctrl+I)", text: "ک" },
    { format: "heading", label: "عنوان", title: "عنوان بخش", text: "عنوان" },
    { format: "list", label: "فهرست", title: "فهرست نشانه‌دار", text: "فهرست" },
    { format: "link", label: "پیوند", title: "افزودن پیوند", text: "پیوند" },
  ];

  function wrap(textarea, before, after, placeholder) {
    var start = textarea.selectionStart;
    var end = textarea.selectionEnd;
    var value = textarea.value;
    var selected = value.slice(start, end) || placeholder;
    textarea.value = value.slice(0, start) + before + selected + after + value.slice(end);
    textarea.focus();
    var selectionStart = start + before.length;
    textarea.setSelectionRange(selectionStart, selectionStart + selected.length);
    textarea.dispatchEvent(new Event("input", { bubbles: true }));
  }

  function applyFormat(textarea, format) {
    switch (format) {
      case "bold":
        wrap(textarea, "<strong>", "</strong>", "متن پررنگ");
        break;
      case "italic":
        wrap(textarea, "<em>", "</em>", "متن مورب");
        break;
      case "heading":
        wrap(textarea, "<h2>", "</h2>", "عنوان بخش");
        break;
      case "list":
        wrap(textarea, "<ul>\n  <li>", "</li>\n  <li>مورد دوم</li>\n</ul>", "مورد اول");
        break;
      case "link": {
        var url = window.prompt("نشانی پیوند را وارد کنید (مثال: https://cusin.ir):", "https://");
        if (!url) return;
        var safe = /^(https?:\/\/|\/|#|mailto:|tel:)/i.test(url.trim());
        if (!safe) {
          window.alert("فقط نشانی‌های http، https، mailto، tel یا مسیر داخلی مجاز است.");
          return;
        }
        wrap(textarea, '<a href="' + url.trim() + '">', "</a>", "متن پیوند");
        break;
      }
      default:
        break;
    }
  }

  function buildToolbar(textarea) {
    var toolbar = document.createElement("div");
    toolbar.className = "cusin-rich-text-toolbar";
    toolbar.setAttribute("role", "toolbar");
    toolbar.setAttribute("aria-label", "قالب‌بندی متن");

    BUTTONS.forEach(function (item) {
      var button = document.createElement("button");
      button.type = "button";
      button.className = "cusin-rich-text-btn";
      button.textContent = item.text;
      button.title = item.title;
      button.setAttribute("aria-label", item.label);
      button.setAttribute("data-cusin-format", item.format);
      button.addEventListener("click", function () {
        applyFormat(textarea, item.format);
      });
      toolbar.appendChild(button);
    });

    var hint = document.createElement("span");
    hint.className = "cusin-rich-text-hint";
    hint.textContent = "برای پیوند، ابتدا متن را انتخاب کنید.";
    toolbar.appendChild(hint);
    return toolbar;
  }

  function init() {
    document.querySelectorAll("textarea[data-cusin-rich-text]").forEach(function (textarea) {
      if (textarea.dataset.cusinRichTextReady === "1") return;
      textarea.dataset.cusinRichTextReady = "1";
      textarea.parentNode.insertBefore(buildToolbar(textarea), textarea);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () { setTimeout(init, 0); });
  } else {
    setTimeout(init, 0);
  }
})();
