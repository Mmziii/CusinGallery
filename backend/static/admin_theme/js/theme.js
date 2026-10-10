/* کازین گالری — admin theme behaviours (Part A/B, vanilla JS, no deps).
 *
 * Progressive enhancement only: every feature degrades to plain links /
 * plain tables when JS is unavailable. Sections:
 *   1. sidebar drawer (mobile)          5. changelist mobile card labels
 *   2. user menu auto-close             6. quick status tracking guard (B3c)
 *   3. global quick-search palette (B6) 7. misc polish
 *   4. copy-to-clipboard buttons
 */
(function () {
  "use strict";

  var prefersReducedMotion = window.matchMedia &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* Scroll lock shared by the drawer and the palette. The page scrolls
   * again only when no overlay still needs the lock. */
  var overlayLocks = 0;
  function lockBodyScroll() {
    overlayLocks += 1;
    document.body.style.overflow = "hidden";
  }
  function unlockBodyScroll() {
    overlayLocks = Math.max(0, overlayLocks - 1);
    if (!overlayLocks) document.body.style.overflow = "";
  }

  /* ------------------------------------------------------------------ *
   * 1. Sidebar drawer
   * ------------------------------------------------------------------ */
  function initDrawer() {
    var toggle = document.getElementById("cusin-drawer-toggle");
    var drawer = document.getElementById("cusin-drawer");
    var scrim = document.querySelector("[data-cusin-drawer-scrim]");
    if (!toggle || !drawer) return;

    function setOpen(open) {
      var wasOpen = drawer.classList.contains("is-open");
      if (open === wasOpen) return;
      drawer.classList.toggle("is-open", open);
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
      if (scrim) scrim.hidden = !open;
      if (open) lockBodyScroll(); else unlockBodyScroll();
    }
    toggle.addEventListener("click", function () {
      setOpen(!drawer.classList.contains("is-open"));
    });
    if (scrim) scrim.addEventListener("click", function () { setOpen(false); });
    document.addEventListener("keydown", function (event) {
      if (event.key !== "Escape" || !drawer.classList.contains("is-open")) return;
      // the palette sits on top of the drawer, so Escape closes it first
      if (document.querySelector("[data-cusin-palette]:not([hidden])")) return;
      setOpen(false);
    });
    // Close the drawer when a link inside it is activated (mobile SPA-ish feel)
    drawer.addEventListener("click", function (event) {
      if (event.target.closest && event.target.closest("a") && window.innerWidth <= 1024) {
        setOpen(false);
      }
    });
  }

  /* ------------------------------------------------------------------ *
   * 2. User menu: close on outside click / Escape
   * ------------------------------------------------------------------ */
  function initMenus() {
    var menus = document.querySelectorAll("[data-cusin-menu]");
    if (!menus.length) return;
    document.addEventListener("click", function (event) {
      menus.forEach(function (menu) {
        if (!menu.contains(event.target)) menu.removeAttribute("open");
      });
    });
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape") menus.forEach(function (m) { m.removeAttribute("open"); });
    });
  }

  /* ------------------------------------------------------------------ *
   * 3. Quick-search palette (B6)
   * ------------------------------------------------------------------ */
  function initPalette() {
    var root = document.querySelector("[data-cusin-palette]");
    var opener = document.querySelector("[data-cusin-search-open]");
    if (!root || !opener) return;

    var input = root.querySelector("[data-cusin-palette-input]");
    var results = root.querySelector("[data-cusin-palette-results]");
    var closeEls = root.querySelectorAll("[data-cusin-palette-close]");
    var endpoint = opener.getAttribute("data-search-url") ||
      document.body.getAttribute("data-cusin-search-url") || "";
    var debounceTimer = null;
    var activeIndex = -1;
    var rows = [];
    var lastQuery = "";

    var GROUP_ICONS = {
      orders: "receipt", products: "box", customers: "users", sections: "grid"
    };

    function sprite(name) {
      return '<svg class="cusin-icon" aria-hidden="true" focusable="false">' +
        '<use href="#cusin-i-' + name + '"></use></svg>';
    }
    function escapeHtml(text) {
      var div = document.createElement("div");
      div.textContent = text == null ? "" : String(text);
      return div.innerHTML;
    }

    function isOpen() {
      return !root.hidden;
    }
    function openPalette() {
      if (isOpen()) return;
      // remember where the user was so closing returns them there
      returnFocus = document.activeElement;
      root.hidden = false;
      lockBodyScroll();
      input.value = "";
      lastQuery = "";
      renderEmptyState("برای جستجو دست‌کم ۲ حرف بنویسید…");
      input.focus();
    }
    function closePalette(options) {
      if (!isOpen()) return;
      var restore = !options || options.restoreFocus !== false;
      var target = returnFocus;
      returnFocus = null;
      root.hidden = true;
      unlockBodyScroll();
      if (restore && target && target !== document.body && target.isConnected) {
        target.focus();
      }
    }
    // Silent reset for pagehide: a back/forward-cache restore must not
    // bring back a palette that was open when the user left the page.
    function resetPalette() {
      window.clearTimeout(debounceTimer);
      if (isOpen()) {
        root.hidden = true;
        unlockBodyScroll();
      }
      returnFocus = null;
    }
    // Choosing a result closes the palette first, so a same-page (hash)
    // link does not leave it open behind the new location.
    function openResult(url) {
      closePalette({ restoreFocus: false });
      window.location.href = url;
    }
    // Keep Tab inside the open palette: the input and the result links.
    function trapTab(event) {
      var items = [input].concat(rows);
      var current = items.indexOf(document.activeElement);
      var step = event.shiftKey ? -1 : 1;
      var next = current === -1 ? 0 : (current + step + items.length) % items.length;
      event.preventDefault();
      items[next].focus();
    }
    var returnFocus = null;

    function renderEmptyState(message) {
      results.innerHTML = '<div class="cusin-palette-empty">' + escapeHtml(message) + "</div>";
      rows = [];
      activeIndex = -1;
    }

    function renderGroups(data) {
      var html = "";
      var count = 0;
      (data.groups || []).forEach(function (group) {
        if (!group.results || !group.results.length) return;
        html += '<div class="cusin-pgroup-label">' + escapeHtml(group.label) + "</div>";
        group.results.forEach(function (item) {
          var icon = GROUP_ICONS[group.id] || "dot";
          html +=
            '<a class="cusin-prow" role="option" aria-selected="false" href="' +
            escapeHtml(item.url) + '">' +
            '<span class="cusin-prow-icon">' + sprite(icon) + "</span>" +
            '<span class="cusin-prow-body">' +
            '<span class="cusin-prow-title">' + escapeHtml(item.title) + "</span>" +
            (item.subtitle ? '<span class="cusin-prow-sub">' + escapeHtml(item.subtitle) + "</span>" : "") +
            "</span></a>";
          count += 1;
        });
      });
      if (!count) {
        renderEmptyState("نتیجه‌ای پیدا نشد.");
        return;
      }
      results.innerHTML = html;
      rows = Array.prototype.slice.call(results.querySelectorAll(".cusin-prow"));
      activeIndex = -1;
    }

    function setActive(index) {
      if (!rows.length) return;
      if (index < 0) index = rows.length - 1;
      if (index >= rows.length) index = 0;
      rows.forEach(function (row, i) {
        row.classList.toggle("is-active", i === index);
        row.setAttribute("aria-selected", i === index ? "true" : "false");
        if (i === index) row.scrollIntoView({ block: "nearest" });
      });
      activeIndex = index;
    }

    function fetchResults(query) {
      if (!endpoint) return;
      fetch(endpoint + "?q=" + encodeURIComponent(query), {
        headers: { "X-Requested-With": "XMLHttpRequest" },
        credentials: "same-origin"
      }).then(function (response) {
        if (response.status === 429) {
          renderEmptyState("تعداد درخواست‌ها زیاد است؛ چند لحظه صبر کنید.");
          return null;
        }
        if (!response.ok) throw new Error("HTTP " + response.status);
        return response.json();
      }).then(function (data) {
        if (data) renderGroups(data);
      }).catch(function () {
        renderEmptyState("جستجو در دسترس نیست؛ اتصال را بررسی کنید.");
      });
    }

    input.addEventListener("input", function () {
      var query = input.value.trim();
      if (query === lastQuery) return;
      lastQuery = query;
      window.clearTimeout(debounceTimer);
      if (query.length < 2) {
        renderEmptyState("برای جستجو دست‌کم ۲ حرف بنویسید…");
        return;
      }
      renderEmptyState("در حال جستجو…");
      debounceTimer = window.setTimeout(function () { fetchResults(query); }, 250);
    });

    input.addEventListener("keydown", function (event) {
      if (event.key === "ArrowDown") { event.preventDefault(); setActive(activeIndex + 1); }
      else if (event.key === "ArrowUp") { event.preventDefault(); setActive(activeIndex - 1); }
      else if (event.key === "Enter") {
        event.preventDefault();
        if (activeIndex >= 0 && rows[activeIndex]) openResult(rows[activeIndex].href);
      }
      // Escape is handled at document level so it works from any focus.
    });

    results.addEventListener("click", function (event) {
      var row = event.target.closest ? event.target.closest(".cusin-prow") : null;
      if (row) {
        event.preventDefault();
        openResult(row.href);
      }
    });
    results.addEventListener("mousemove", function (event) {
      var row = event.target.closest ? event.target.closest(".cusin-prow") : null;
      if (row) setActive(rows.indexOf(row));
    });

    closeEls.forEach(function (el) { el.addEventListener("click", function () { closePalette(); }); });
    opener.addEventListener("click", openPalette);
    window.addEventListener("pagehide", resetPalette);
    document.addEventListener("keydown", function (event) {
      if (isOpen()) {
        if (event.key === "Escape") {
          event.preventDefault();
          closePalette();
          return;
        }
        if (event.key === "Tab") {
          trapTab(event);
          return;
        }
      }
      var tag = (event.target.tagName || "").toLowerCase();
      var typing = tag === "input" || tag === "textarea" || tag === "select" ||
        event.target.isContentEditable;
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        if (isOpen()) closePalette(); else openPalette();
        return;
      }
      if (event.key === "/" && !typing && !isOpen() && !event.ctrlKey && !event.metaKey) {
        event.preventDefault();
        openPalette();
      }
    });
  }

  /* ------------------------------------------------------------------ *
   * 4. Copy-to-clipboard buttons: <button data-cusin-copy="TEXT">
   * ------------------------------------------------------------------ */
  function initCopyButtons() {
    document.addEventListener("click", function (event) {
      var btn = event.target.closest ? event.target.closest("[data-cusin-copy]") : null;
      if (!btn) return;
      event.preventDefault();
      var text = btn.getAttribute("data-cusin-copy") || "";
      var done = function () {
        var old = btn.getAttribute("data-cusin-copy-label") || btn.innerHTML;
        btn.setAttribute("data-cusin-copy-label", old);
        btn.textContent = "کپی شد";
        btn.classList.add("is-copied");
        window.setTimeout(function () {
          btn.innerHTML = btn.getAttribute("data-cusin-copy-label") || "کپی";
          btn.classList.remove("is-copied");
        }, 1600);
      };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(done, function () { /* ignored */ });
      } else {
        var area = document.createElement("textarea");
        area.value = text;
        area.setAttribute("readonly", "");
        area.style.position = "fixed";
        area.style.opacity = "0";
        document.body.appendChild(area);
        area.select();
        try { document.execCommand("copy"); done(); } catch (err) { /* ignored */ }
        document.body.removeChild(area);
      }
    });
  }

  /* ------------------------------------------------------------------ *
   * 5. Changelist mobile cards: mirror header text into td[data-label]
   * ------------------------------------------------------------------ */
  function initCardLabels() {
    document.querySelectorAll("#result_list, .cusin-items-table").forEach(function (table) {
      var headers = Array.prototype.map.call(
        table.querySelectorAll("thead th"),
        function (th) { return th.textContent.trim(); }
      );
      table.querySelectorAll("tbody tr").forEach(function (tr) {
        Array.prototype.forEach.call(tr.children, function (cell, index) {
          if (!cell.hasAttribute("data-label") && headers[index]) {
            cell.setAttribute("data-label", headers[index]);
          }
        });
      });
    });
  }

  /* ------------------------------------------------------------------ *
   * 6. Quick status buttons (B3c): «ارسال شده» needs a tracking code
   *    when the order is a courier order. Progressive guard only: the
   *    server enforces the same rule; this focuses the empty field first
   *    so the owner does not wait for a round trip.
   * ------------------------------------------------------------------ */
  function initQuickStatusGuard() {
    document.querySelectorAll("form.cusin-quick-form").forEach(function (form) {
      var tracking = form.querySelector('input[name="tracking_code"]');
      if (!tracking) return;
      tracking.addEventListener("input", function () {
        tracking.removeAttribute("aria-invalid");
      });
      form.querySelectorAll('button[name="next_status"]').forEach(function (button) {
        button.addEventListener("click", function (event) {
          if (button.value === "shipped" && !tracking.value.trim()) {
            event.preventDefault();
            tracking.setAttribute("aria-invalid", "true");
            tracking.focus();
          }
        });
      });
    });
  }

  /* ------------------------------------------------------------------ *
   * 7. Misc polish
   * ------------------------------------------------------------------ */
  function initMisc() {
    // Smooth in-page anchor scrolling unless reduced motion is requested.
    if (!prefersReducedMotion) {
      document.documentElement.classList.add("cusin-smooth");
    }
    // Autofocus the changelist search on "/" is handled by the palette;
    // keep Django's own search form untouched.
  }

  document.addEventListener("DOMContentLoaded", function () {
    initDrawer();
    initMenus();
    initPalette();
    initCopyButtons();
    initCardLabels();
    initQuickStatusGuard();
    initMisc();
  });
})();
