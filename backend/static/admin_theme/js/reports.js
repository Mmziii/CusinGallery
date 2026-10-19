/* «گزارش‌ها و تحلیل» helpers (Task 2/3).
 *
 *  - the per-row «کپی» button copies the customer's phone (Clipboard API,
 *    with a graceful fallback for browsers without it);
 *  - feedback is announced through a live region, never an alert.
 *
 * No new library: plain DOM only, loaded with `defer` by the report page.
 */
(function () {
  "use strict";

  var LIVE_TEXT = "کپی شد";

  function announce(button) {
    var original = button.getAttribute("data-original-label") || button.textContent;
    button.setAttribute("data-original-label", original);
    button.textContent = LIVE_TEXT;
    button.classList.add("is-copied");
    window.setTimeout(function () {
      button.textContent = original;
      button.classList.remove("is-copied");
    }, 1600);
  }

  function fallbackCopy(text) {
    var area = document.createElement("textarea");
    area.value = text;
    area.setAttribute("readonly", "");
    area.style.position = "fixed";
    area.style.opacity = "0";
    document.body.appendChild(area);
    area.select();
    try {
      document.execCommand("copy");
    } catch (error) {
      /* nothing else to try; the button simply does nothing */
    }
    document.body.removeChild(area);
  }

  function copy(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(text);
    }
    fallbackCopy(text);
    return Promise.resolve();
  }

  document.addEventListener("click", function (event) {
    var button = event.target.closest("[data-cusin-copy]");
    if (!button) return;
    var value = button.getAttribute("data-cusin-copy") || "";
    if (!value) return;
    copy(value).then(function () {
      announce(button);
    }).catch(function () {
      /* clipboard denied: leave the button untouched */
    });
  });
})();
