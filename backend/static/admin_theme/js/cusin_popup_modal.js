/* کازین گالری — درون‌صفحه‌ای modal برای RelatedObjectLookups (Task 1).
 *
 * Replace every Django related-object "+ / edit / view / lookup" popup
 * (window.open) with an in-page modal dialog: dimmed backdrop, centered
 * panel (max 960px x 90vh, rounded, light theme), title bar with page
 * title and close (x), popup page inside an iframe, fade + scale
 * transition (respecting prefers-reduced-motion), Escape and backdrop
 * click close ("تغییرات ذخیره نشده‌اند؛ بسته شود؟" if form dirty).
 *
 * After saving inside the modal, the new/changed object is selected in
 * the original field exactly like Django's popup flow
 * (dismissAddRelatedObjectPopup / dismissChangeRelatedObjectPopup,
 * including autocomplete/select2 and filter_horizontal widgets), then
 * the modal closes. On phones the modal is full-screen.
 *
 * Interrupt points (Django 5.2 RelatedObjectLookups.js):
 *  - its delegated click handler fires django:show-related /
 *    django:lookup-related jQuery events and only calls the lexical
 *    showRelatedObjectPopup when they are not default-prevented, so
 *    preventing those events is the supported way to replace
 *    window.open (overriding window.showRelatedObjectPopup alone does
 *    NOT intercept the delegated handler, which calls the lexical
 *    function directly). We also keep window.* overrides for code
 *    that calls them programmatically, plus a capture-phase fallback
 *    for dynamically added rows and for view-related links (which
 *    Django does not mark data-popup="yes").
 *  - saving renders popup_response.html. This project overrides that
 *    template (templates/admin/popup_response.html): inside the modal
 *    iframe it never loads Django's popup_response.js, so window.opener
 *    is never touched and the old
 *    "Cannot read properties of null (reading 'dismissAddRelatedObjectPopup')"
 *    console error cannot happen. On iframe load we read the documented
 *    data-popup-response JSON and invoke the matching dismiss handler
 *    with a synthetic win object.
 */
(function () {
  "use strict";

  var prefersReducedMotion = window.matchMedia &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  var modal, backdrop, panel, titleEl, iframe, closeBtn;
  var isOpen = false;
  var returnFocus = null;
  var currentPopupName = null;
  var reloadOnSave = false;
  var initialSnapshot = null;
  var snapshotTimer = null;
  var closeGeneration = 0;
  var initialized = false;

  function lockBodyScroll() {
    if (typeof window.cusinLockBodyScroll === "function") {
      window.cusinLockBodyScroll();
      return;
    }
    document.body.style.overflow = "hidden";
  }
  function unlockBodyScroll() {
    if (typeof window.cusinUnlockBodyScroll === "function") {
      window.cusinUnlockBodyScroll();
      return;
    }
    document.body.style.overflow = "";
  }

  function ensureModalDOM() {
    if (modal) return;
    modal = document.createElement("div");
    modal.className = "cusin-modal";
    modal.id = "cusin-related-modal";
    modal.setAttribute("hidden", "");
    modal.setAttribute("aria-hidden", "true");

    backdrop = document.createElement("div");
    backdrop.className = "cusin-modal-backdrop";
    backdrop.setAttribute("data-cusin-modal-close", "");

    panel = document.createElement("div");
    panel.className = "cusin-modal-panel";
    panel.setAttribute("role", "dialog");
    panel.setAttribute("aria-modal", "true");
    panel.setAttribute("aria-labelledby", "cusin-modal-title");

    var head = document.createElement("div");
    head.className = "cusin-modal-head";

    titleEl = document.createElement("h2");
    titleEl.className = "cusin-modal-title";
    titleEl.id = "cusin-modal-title";
    titleEl.textContent = "";

    closeBtn = document.createElement("button");
    closeBtn.type = "button";
    closeBtn.className = "cusin-modal-close";
    closeBtn.setAttribute("aria-label", "بستن");
    closeBtn.setAttribute("data-cusin-modal-close", "");
    closeBtn.textContent = "×";

    head.appendChild(titleEl);
    head.appendChild(closeBtn);

    var body = document.createElement("div");
    body.className = "cusin-modal-body";

    iframe = document.createElement("iframe");
    iframe.className = "cusin-modal-iframe";

    body.appendChild(iframe);
    panel.appendChild(head);
    panel.appendChild(body);
    modal.appendChild(backdrop);
    modal.appendChild(panel);
    document.body.appendChild(modal);

    backdrop.addEventListener("click", requestClose);
    closeBtn.addEventListener("click", requestClose);
    modal.addEventListener("click", function (e) {
      if (e.target === modal) requestClose();
    });
    iframe.addEventListener("load", onIframeLoad);
  }

  function serializeIframeForms() {
    try {
      var doc = iframe.contentDocument;
      if (!doc) return "";
      var parts = [];
      doc.querySelectorAll("form").forEach(function (form) {
        Array.prototype.forEach.call(form.elements, function (el) {
          if (!el.name || el.disabled) return;
          if (el.type === "submit" || el.type === "button") return;
          if ((el.type === "checkbox" || el.type === "radio")) {
            parts.push(el.name + "=" + (el.checked ? el.value : ""));
          } else if (el.type === "file") {
            parts.push(el.name + "=" + (el.files && el.files.length ? el.files[0].name : ""));
          } else if (el.tagName === "SELECT" && el.multiple) {
            var vals = Array.prototype.map.call(el.selectedOptions, function (o) { return o.value; });
            parts.push(el.name + "=" + vals.join(","));
          } else {
            parts.push(el.name + "=" + (el.value || ""));
          }
        });
      });
      return parts.join("&");
    } catch (e) {
      return "";
    }
  }

  function isIframeDirty() {
    if (initialSnapshot === null) return false;
    return serializeIframeForms() !== initialSnapshot;
  }

  function requestClose() {
    if (!isOpen) return;
    if (isIframeDirty()) {
      if (!window.confirm("تغییرات ذخیره نشده‌اند؛ بسته شود؟")) return;
    }
    closeModal();
  }

  function openModal(triggeringLink, href, popupName, title) {
    ensureModalDOM();
    if (isOpen) {
      // A second open while one is live should replace its content
      // rather than stacking scroll locks.
      closeGeneration += 1;
    } else {
      returnFocus = document.activeElement;
    }
    currentPopupName = popupName || "";
    reloadOnSave = !!(triggeringLink && triggeringLink.dataset && triggeringLink.dataset.cusinModalReload);
    titleEl.textContent = title || (triggeringLink && (triggeringLink.getAttribute("aria-label") || triggeringLink.getAttribute("title"))) || "افزودن";
    iframe.setAttribute("title", titleEl.textContent);
    iframe.name = popupName || "";
    iframe.src = href;
    modal.hidden = false;
    modal.removeAttribute("hidden");
    modal.setAttribute("aria-hidden", "false");
    if (!prefersReducedMotion) {
      modal.classList.remove("is-open");
      void modal.offsetHeight;
    }
    modal.classList.add("is-open");
    isOpen = true;
    initialSnapshot = null;
    lockBodyScroll();
    setTimeout(function () { if (closeBtn) closeBtn.focus(); }, 50);
  }

  function closeModal() {
    if (!isOpen) return;
    isOpen = false;
    modal.classList.remove("is-open");
    var generation = ++closeGeneration;
    var delay = prefersReducedMotion ? 0 : 180;
    var focusTarget = returnFocus;
    returnFocus = null;
    setTimeout(function () {
      if (generation !== closeGeneration || isOpen) return;
      modal.hidden = true;
      modal.setAttribute("hidden", "");
      modal.setAttribute("aria-hidden", "true");
      iframe.src = "about:blank";
      unlockBodyScroll();
      currentPopupName = null;
      initialSnapshot = null;
      if (focusTarget && focusTarget.isConnected) focusTarget.focus();
    }, delay);
  }

  // ---------------------------------------------------------------------------
  // Iframe load: popup-response detection, title, dirty snapshot, Escape.
  // ---------------------------------------------------------------------------
  function onIframeLoad() {
    if (!isOpen) return;
    var doc, win;
    try {
      win = iframe.contentWindow;
      doc = iframe.contentDocument || (win && win.document);
    } catch (e) { return; }
    if (!doc || !win) return;
    // about:blank after close
    if (doc.URL === "about:blank") return;

    var popupResponseEl = doc.getElementById("django-admin-popup-response-constants");
    if (popupResponseEl) {
      var dataAttr = popupResponseEl.getAttribute("data-popup-response") ||
        (popupResponseEl.dataset && popupResponseEl.dataset.popupResponse);
      if (dataAttr) {
        try {
          handlePopupResponse(JSON.parse(dataAttr));
          return;
        } catch (e) { /* fall through to plain close below */ }
      }
    }

    var h1 = doc.querySelector("#content h1");
    if (h1 && h1.textContent.trim()) {
      titleEl.textContent = h1.textContent.trim();
    } else if (doc.title) {
      var cleanTitle = doc.title.split(" | ")[0].trim();
      if (cleanTitle) titleEl.textContent = cleanTitle;
    }
    iframe.setAttribute("title", titleEl.textContent);

    // Keep window.name in sync so nested popups compute __2, __3...
    try { if (currentPopupName) win.name = currentPopupName; } catch (e) {}
    // Deliberately NO window.opener proxy: the iframe flow must never touch
    // opener (it is null in an iframe and caused the console error fixed by
    // templates/admin/popup_response.html). The popup response JSON is read
    // by handlePopupResponse above.

    // Raw-id lookup chooser links inside the iframe.
    doc.querySelectorAll("a[data-popup-opener]").forEach(function (link) {
      link.addEventListener("click", function (e) {
        e.preventDefault();
        dismissRelatedLookup({ name: win.name || currentPopupName || "" }, link.getAttribute("data-popup-opener"));
      });
    });

    // Escape pressed while focus is inside the iframe must close the
    // modal (the parent document never sees that keydown).
    doc.addEventListener("keydown", function (e) {
      if (e.key === "Escape") {
        // If something inside already handled it (e.g. an open menu
        // called preventDefault + stopPropagation in an earlier
        // listener), respect that.
        if (e.defaultPrevented) return;
        e.preventDefault();
        requestClose();
      }
    });

    // Snapshot AFTER Django admin JS has initialised widgets (it fires
    // synthetic change events on load, e.g. related-widget select
    // trigger), otherwise every untouched form would read as dirty.
    if (snapshotTimer) clearTimeout(snapshotTimer);
    snapshotTimer = setTimeout(function () {
      initialSnapshot = serializeIframeForms();
    }, 350);
    // Saving navigates to the popup-response page; never warn then.
    doc.querySelectorAll("form").forEach(function (form) {
      form.addEventListener("submit", function () { initialSnapshot = serializeIframeForms(); });
    });
  }

  function handlePopupResponse(initData) {
    var fakeWin = {
      name: currentPopupName || iframe.name || "",
      location: {
        pathname: (function () {
          try { return new URL(iframe.src, window.location.origin).pathname; }
          catch (e) { return iframe.src || ""; }
        })()
      },
      close: function () { closeModal(); }
    };
    if (initData.action === "change") {
      dismissChangeRelatedObjectPopup(fakeWin, initData.value, initData.obj, initData.new_value);
    } else if (initData.action === "delete") {
      dismissDeleteRelatedObjectPopup(fakeWin, initData.value);
    } else {
      dismissAddRelatedObjectPopup(fakeWin, initData.value, initData.obj);
    }
    if (isOpen) closeModal();
    if (reloadOnSave) {
      // Changelist "+ زیردسته" style links: there is no form field to
      // fill, the new row simply has to appear in the list.
      reloadOnSave = false;
      window.location.reload();
    }
  }

  // ---------------------------------------------------------------------------
  // Dismiss handlers (adapted from Django's RelatedObjectLookups.js).
  // ---------------------------------------------------------------------------
  function getDjangoJQuery() {
    return (window.django && window.django.jQuery) || window.jQuery || null;
  }
  function triggerChange(elem) {
    var $ = getDjangoJQuery();
    if ($) $(elem).trigger("change");
    else elem.dispatchEvent(new Event("change", { bubbles: true }));
  }
  function esc(id) {
    return window.CSS && CSS.escape ? CSS.escape(id) : id.replace(/([ !"#$%&'()*+,./:;<=>?@[\\\]^`{|}~])/g, "\\$1");
  }

  function updateRelatedSelectsOptions(currentSelect, win, objId, newRepr, newId, skipIds) {
    if (!currentSelect) return;
    skipIds = skipIds || [];
    var path = (win.location && win.location.pathname) || "";
    var parts = path.split("/");
    var modelName = parts[parts.length - (objId ? 4 : 3)];
    var selector = modelName
      ? '[data-model-ref="' + modelName + '"] [data-context="available-source"]'
      : '[data-model-ref] [data-context="available-source"]';
    document.querySelectorAll(selector).forEach(function (select) {
      if (currentSelect === select || skipIds.indexOf(select.id) !== -1) return;
      var option = select.querySelector('option[value="' + String(objId).replace(/"/g, "") + '"]');
      if (!option) {
        option = new Option(newRepr, newId);
        select.options.add(option);
        if (window.SelectBox !== undefined && !window.SelectBox.cache[currentSelect.id]) {
          window.SelectBox.add_to_cache(select.id, option);
          window.SelectBox.redisplay(select.id);
        }
        return;
      }
      option.textContent = newRepr;
      option.value = newId;
    });
  }

  function dismissAddRelatedObjectPopup(win, newId, newRepr) {
    var name = removePopupIndex(win.name);
    var elem = document.getElementById(name);
    if (elem) {
      var elemName = elem.nodeName.toUpperCase();
      if (elemName === "SELECT") {
        // Avoid duplicating the option when select2/autocomplete has
        // already fetched it; Django's stock handler always appends,
        // so mirror it but select the existing one if present.
        var existing = elem.querySelector('option[value="' + String(newId).replace(/"/g, "") + '"]');
        if (existing) { existing.textContent = newRepr; elem.value = newId; }
        else elem.options[elem.options.length] = new Option(newRepr, newId, true, true);
        updateRelatedSelectsOptions(elem, win, null, newRepr, newId);
      } else if (elemName === "INPUT") {
        if (elem.classList.contains("vManyToManyRawIdAdminField") && elem.value) {
          elem.value += "," + newId;
        } else {
          elem.value = newId;
        }
      }
      triggerChange(elem);
    } else {
      var toId = name + "_to";
      var toElem = document.getElementById(toId);
      if (window.SelectBox) {
        window.SelectBox.add_to_cache(toId, new Option(newRepr, newId));
        window.SelectBox.redisplay(toId);
        if (toElem && toElem.nodeName.toUpperCase() === "SELECT") {
          updateRelatedSelectsOptions(toElem, win, null, newRepr, newId, [name + "_from"]);
        }
      } else if (toElem) {
        toElem.options[toElem.options.length] = new Option(newRepr, newId, true, true);
        triggerChange(toElem);
      }
    }
    closeModal();
  }

  function dismissChangeRelatedObjectPopup(win, objId, newRepr, newId) {
    var id = removePopupIndex(String(win.name || "").replace(/^edit_/, ""));
    var selector = "#" + esc(id) + ", #" + esc(id + "_from") + ", #" + esc(id + "_to");
    var selects = document.querySelectorAll(selector);
    selects.forEach(function (select) {
      select.querySelectorAll("option").forEach(function (opt) {
        if (opt.value === String(objId)) {
          opt.textContent = newRepr;
          opt.value = newId;
        }
      });
      triggerChange(select);
      // select2 rendered label next to the (hidden) select.
      var next = select.nextElementSibling;
      if (next) {
        next.querySelectorAll(".select2-selection__rendered").forEach(function (el) {
          if (el.lastChild) el.lastChild.textContent = newRepr;
          el.title = newRepr;
        });
      }
    });
    updateRelatedSelectsOptions(selects[0], win, objId, newRepr, newId);
    closeModal();
  }

  function dismissRelatedLookup(win, chosenId) {
    var name = removePopupIndex(win.name);
    var elem = document.getElementById(name);
    if (elem) {
      if (elem.classList.contains("vManyToManyRawIdAdminField") && elem.value) {
        elem.value += "," + chosenId;
      } else {
        elem.value = chosenId;
      }
      triggerChange(elem);
    }
    closeModal();
  }

  function dismissDeleteRelatedObjectPopup(win, objId) {
    var id = removePopupIndex(String(win.name || "").replace(/^delete_/, ""));
    var selector = "#" + esc(id) + ", #" + esc(id + "_from") + ", #" + esc(id + "_to");
    document.querySelectorAll(selector).forEach(function (select) {
      select.querySelectorAll('option[value="' + String(objId).replace(/"/g, "") + '"]').forEach(function (opt) { opt.remove(); });
      triggerChange(select);
    });
    closeModal();
  }

  function getPopupIndex() {
    if (document.getElementsByName("_popup").length > 0) {
      var idx = window.name.lastIndexOf("__") + 2;
      var parsed = parseInt(window.name.substring(idx), 10);
      return isNaN(parsed) ? 0 : parsed;
    }
    return 0;
  }
  function removePopupIndex(name) {
    // Our names always carry exactly one "__<n>" suffix; strip any of
    // them (more forgiving than Django's exact-index strip when the
    // modal introduced an extra nesting level).
    return String(name || "").replace(/__\d+$/, "");
  }
  function addPopupIndex(name) {
    return name + "__" + (getPopupIndex() + 1);
  }

  // ---------------------------------------------------------------------------
  // Opening: the three interception layers described at the top.
  // ---------------------------------------------------------------------------
  function hrefWithPopup(href) {
    try {
      var url = new URL(href, window.location.origin);
      url.searchParams.set("_popup", "1");
      return url.toString();
    } catch (e) {
      if (href.indexOf("_popup") === -1) href += (href.indexOf("?") === -1 ? "?" : "&") + "_popup=1";
      return href;
    }
  }

  function openFromLink(link, nameRegexp) {
    if (!link || link.getAttribute("aria-disabled") === "true") return false;
    var href = link.getAttribute("href");
    if (!href || href === "#") return false;
    var rawName = (link.id || "").replace(nameRegexp, "");
    var name = rawName ? addPopupIndex(rawName) : "";
    var title = link.getAttribute("aria-label") || link.getAttribute("title") || "";
    openModal(link, hrefWithPopup(link.href), name, title);
    return false;
  }

  function initOverride() {
    if (initialized) return;
    initialized = true;

    window.dismissAddRelatedObjectPopup = dismissAddRelatedObjectPopup;
    window.dismissChangeRelatedObjectPopup = dismissChangeRelatedObjectPopup;
    window.dismissDeleteRelatedObjectPopup = dismissDeleteRelatedObjectPopup;
    window.dismissAddAnotherPopup = dismissAddRelatedObjectPopup;
    window.dismissRelatedLookupPopup = function (win, chosenId) {
      if (isOpen) dismissRelatedLookup(win, chosenId);
      // No modal open (should not happen): nothing sensible to do
      // without a real popup window.
    };
    window.showRelatedObjectPopup = function (link) { return openFromLink(link, /^(change|add|delete)_/); };
    window.showRelatedObjectLookupPopup = function (link) { return openFromLink(link, /^lookup_/); };
    window.showAddAnotherPopup = window.showRelatedObjectPopup;
    // Exposed for tests / debugging and for category "+ زیردسته" links.
    window.cusinOpenRelatedModal = function (linkOrHref, title) {
      if (typeof linkOrHref === "string") {
        openModal(null, hrefWithPopup(linkOrHref), "", title || "");
      } else {
        openFromLink(linkOrHref, /^(change|add|delete|view)_/);
      }
    };

    var $ = getDjangoJQuery();
    if ($) {
      $("body").on("django:show-related", function (event) {
        event.preventDefault();
        openFromLink(event.currentTarget, /^(change|add|delete)_/);
      });
      $("body").on("django:lookup-related", function (event) {
        event.preventDefault();
        openFromLink(event.currentTarget, /^lookup_/);
      });
    }

    // Capture-phase interceptor: covers every related link before
    // Django's (bubble-phase, jQuery-delegated) handler can call
    // window.open. The django:show-related layer above stays as the
    // supported fallback if an event never reaches this listener
    // (e.g. a programmatic jQuery trigger). Also covers view-related
    // links (no data-popup) and explicit opt-ins (data-cusin-modal,
    // e.g. the category "+ زیردسته" buttons).
    document.addEventListener("click", function (event) {
      var link = event.target.closest && event.target.closest(
        '.related-widget-wrapper-link[data-popup="yes"], .related-widget-wrapper-link.view-related, .related-lookup, [data-cusin-modal]'
      );
      if (!link) return;
      if (!link.getAttribute("href") || link.getAttribute("aria-disabled") === "true") return;
      event.preventDefault();
      event.stopPropagation();
      if (link.classList.contains("related-lookup")) {
        openFromLink(link, /^lookup_/);
      } else {
        openFromLink(link, /^(change|add|delete|view)_/);
      }
    }, true);

    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && isOpen) {
        event.preventDefault();
        requestClose();
      }
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () { setTimeout(initOverride, 0); });
  } else {
    setTimeout(initOverride, 0);
  }
})();
