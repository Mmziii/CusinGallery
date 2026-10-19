/* کازین گالری — پل امن صفحهٔ پاسخ پاپ‌آپ (رفع خطای کنسول).
 *
 * چرا این فایل وجود دارد:
 * الگوی پیش‌فرض جنگو (admin/popup_response.html) فایل popup_response.js را
 * داخل سربرگ همین صفحه بارگذاری می‌کند. آن اسکریپت با متغیر سراسری
 * `opener` کار می‌کند؛ داخل iframe مقدار آن null است و بلافاصله خطای
 *   "Cannot read properties of null (reading 'dismissAddRelatedObjectPopup')"
 * در کنسول ثبت می‌شد.
 *
 * رفتار جدید:
 *  - داخل iframe (مودال درون‌صفحه‌ای): هیچ کاری نمی‌کنیم و اصلاً به
 *    window.opener دست نمی‌زنیم؛ داده‌های پاسخ در همان عنصر
 *    data-popup-response هست و اسکریپت مودال (cusin_popup_modal.js) هنگام
 *    load شدن iframe آن را می‌خواند، گزینهٔ تازه را انتخاب و مودال را
 *    می‌بندد.
 *  - پنجرهٔ واقعی (popup مرورگر، مثلاً وقتی تم مدیر خاموش است): رفتار
 *    استاندارد جنگو حفظ می‌شود و popup_response.js فقط وقتی opener واقعی
 *    وجود دارد بارگذاری می‌شود.
 */
(function () {
  "use strict";

  var current = document.currentScript;
  var stockScriptUrl = current
    ? current.getAttribute("data-popup-response-script")
    : "";

  // داخل iframe: مودال والد خودش داده را می‌خواند؛ هیچ ارجاعی به opener.
  if (window.parent && window.parent !== window) return;

  // پنجرهٔ مستقلِ واقعی: فقط اگر opener وجود داشته باشد اسکریپت جنگو را
  // اجرا کن (اسکریپت بدون opener همین خطا را می‌داد).
  if (!window.opener || !stockScriptUrl) return;

  var script = document.createElement("script");
  script.src = stockScriptUrl;
  script.defer = true;
  document.head.appendChild(script);
})();
