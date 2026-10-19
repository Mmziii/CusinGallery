/* کازین گالری — پیش‌نمایش زندهٔ تم فروشگاه در فرم «محتوا و ظاهر سایت».
 *
 * - preset انتخاب‌شده پایه است؛ هر رنگ سفارشیِ پرشده آن را بازنویسی می‌کند
 *   (دقیقاً همان قاعده‌ای که بک‌اند در theme.effective_theme اعمال می‌کند).
 * - گردی دکمه، اندازهٔ متن و سایه هم بلافاصله روی ماکت اعمال می‌شوند.
 * - دکمهٔ «بازگشت به تنظیمات پیش‌فرض» با تأیید کاربر، فرم POST به URL
 *   مخصوص ریست را با توکن CSRF می‌فرستد (بدون تودرتویی form داخل فرم تغییر).
 */
(function () {
  "use strict";

  var RADII = {
    none: "0",
    small: "8px",
    medium: "12px",
    large: "20px",
  };
  var FONT_SIZES = {
    small: "0.9375rem",
    normal: "1rem",
    large: "1.125rem",
  };

  function readPresets() {
    var node = document.getElementById("cusin-theme-presets");
    if (!node) return {};
    try {
      return JSON.parse(node.textContent) || {};
    } catch (e) {
      return {};
    }
  }

  function formField(name) {
    return document.querySelector('[name="' + name + '"]');
  }

  function fieldValue(name) {
    var field = formField(name);
    return field ? String(field.value || "").trim() : "";
  }

  function effectiveColors(presets) {
    var key = fieldValue("theme_preset");
    var preset = presets[key] || presets.olive_gold || {};
    var map = {
      primary: "theme_primary",
      accent: "theme_accent",
      background: "theme_background",
      text: "theme_text",
      header_background: "theme_header_background",
      header_text: "theme_header_text",
      button_text: "theme_button_text",
    };
    var colors = {};
    Object.keys(map).forEach(function (colorKey) {
      var override = fieldValue(map[colorKey]);
      colors[colorKey] = /^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/.test(override)
        ? override
        : preset[colorKey] || "#000000";
    });
    return colors;
  }

  function placeholderColors(presets) {
    var key = fieldValue("theme_preset");
    var preset = presets[key] || presets.olive_gold || {};
    var map = {
      theme_primary: "primary",
      theme_accent: "accent",
      theme_background: "background",
      theme_text: "text",
      theme_header_background: "header_background",
      theme_header_text: "header_text",
      theme_button_text: "button_text",
    };
    Object.keys(map).forEach(function (fieldName) {
      var field = formField(fieldName);
      if (!field) return;
      field.setAttribute("placeholder", preset[map[fieldName]] || "");
    });
  }

  function applyPreview(presets) {
    var frame = document.getElementById("cusin-theme-preview-frame");
    if (!frame) return;
    var colors = effectiveColors(presets);
    var radius = RADII[fieldValue("theme_button_radius")] || RADII.medium;
    var fontSize = FONT_SIZES[fieldValue("theme_base_font_size")] || FONT_SIZES.normal;
    var shadow = fieldValue("theme_card_shadow") === "none" ? "none" : "0 6px 24px rgba(30, 36, 18, 0.10)";

    frame.style.setProperty("--cusin-tp-primary", colors.primary);
    frame.style.setProperty("--cusin-tp-accent", colors.accent);
    frame.style.setProperty("--cusin-tp-bg", colors.background);
    frame.style.setProperty("--cusin-tp-text", colors.text);
    frame.style.setProperty("--cusin-tp-header-bg", colors.header_background);
    frame.style.setProperty("--cusin-tp-header-text", colors.header_text);
    frame.style.setProperty("--cusin-tp-button-text", colors.button_text);
    frame.style.setProperty("--cusin-tp-radius", radius);
    frame.style.setProperty("--cusin-tp-font-size", fontSize);
    frame.style.setProperty("--cusin-tp-shadow", shadow);
    placeholderColors(presets);
  }

  function resetTheme(event) {
    var button = event.currentTarget;
    var url = button.getAttribute("data-reset-url");
    if (!url) return;
    if (!window.confirm(button.getAttribute("data-confirm") || "بازگشت به تنظیمات پیش‌فرض؟")) {
      return;
    }
    var tokenField = document.querySelector('input[name="csrfmiddlewaretoken"]');
    var form = document.createElement("form");
    form.method = "post";
    form.action = url;
    if (tokenField) {
      var token = document.createElement("input");
      token.type = "hidden";
      token.name = "csrfmiddlewaretoken";
      token.value = tokenField.value;
      form.appendChild(token);
    }
    document.body.appendChild(form);
    form.submit();
  }

  function init() {
    var preview = document.getElementById("cusin-theme-preview");
    if (!preview) return;
    var presets = readPresets();
    if (!presets || !Object.keys(presets).length) return;

    var form = document.getElementById("sitesettings_form") || document.querySelector("form");
    if (form) {
      form.addEventListener("input", function () { applyPreview(presets); });
      form.addEventListener("change", function () { applyPreview(presets); });
    }
    var resetButton = document.getElementById("cusin-theme-reset");
    if (resetButton) resetButton.addEventListener("click", resetTheme);
    applyPreview(presets);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () { setTimeout(init, 0); });
  } else {
    setTimeout(init, 0);
  }
})();
