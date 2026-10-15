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
      if (open) {
        lockBodyScroll();
        var firstLink = drawer.querySelector("a, button, summary");
        if (firstLink) firstLink.focus();
      } else {
        unlockBodyScroll();
        toggle.focus();
      }
    }
    toggle.addEventListener("click", function () {
      setOpen(!drawer.classList.contains("is-open"));
    });
    if (scrim) scrim.addEventListener("click", function () { setOpen(false); });
    document.addEventListener("keydown", function (event) {
      if (event.key !== "Escape" || !drawer.classList.contains("is-open")) return;
      // Menus and the palette sit on top of the drawer, so Escape closes
      // the topmost layer first.
      if (activeMenu || document.querySelector("[data-cusin-palette]:not([hidden])")) return;
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
   * 2. Shared menu/popover component
   *
   * Every dropdown uses data-cusin-menu / trigger / panel. Panels are
   * temporarily portalled to body while open so scroll boxes cannot clip
   * them. The same positioning code flips/shifts desktop menus and turns
   * short touch viewports into bottom sheets.
   * ------------------------------------------------------------------ */
  var activeMenu = null;
  var menuSequence = 0;

  function spriteIcon(name) {
    var svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    var use = document.createElementNS("http://www.w3.org/2000/svg", "use");
    svg.setAttribute("class", "cusin-icon");
    svg.setAttribute("aria-hidden", "true");
    svg.setAttribute("focusable", "false");
    use.setAttribute("href", "#cusin-i-" + name);
    svg.appendChild(use);
    return svg;
  }

  function makeMenu(label, id, icon, className) {
    menuSequence += 1;
    var root = document.createElement("div");
    root.className = "cusin-menu" + (className ? " " + className : "");
    root.setAttribute("data-cusin-menu", "");

    var trigger = document.createElement("button");
    trigger.type = "button";
    trigger.className = "cusin-menu-trigger";
    trigger.setAttribute("data-cusin-menu-trigger", "");
    trigger.setAttribute("aria-haspopup", "menu");
    trigger.setAttribute("aria-expanded", "false");
    trigger.id = "cusin-menu-trigger-" + (id || menuSequence);
    trigger.setAttribute("aria-controls", "cusin-menu-panel-" + (id || menuSequence));
    if (icon) trigger.appendChild(spriteIcon(icon));
    var triggerText = document.createElement("span");
    triggerText.textContent = label;
    trigger.appendChild(triggerText);

    var panel = document.createElement("div");
    panel.className = "cusin-menu-panel";
    panel.id = "cusin-menu-panel-" + (id || menuSequence);
    panel.setAttribute("data-cusin-menu-panel", "");
    panel.setAttribute("role", "menu");
    panel.setAttribute("aria-labelledby", trigger.id);
    panel.hidden = true;

    root.appendChild(trigger);
    root.appendChild(panel);
    return { root: root, trigger: trigger, panel: panel };
  }

  function getMenuItems(panel) {
    return Array.prototype.slice.call(panel.querySelectorAll(
      '[role="menuitem"], a[href], button:not([disabled]), summary, [tabindex="0"]'
    )).filter(function (item) {
      return !item.hidden && item.getAttribute("aria-hidden") !== "true";
    });
  }

  function restoreConfirmation(menu) {
    if (!menu || !menu.pending) return;
    menu.panel.replaceChildren(menu.pending.nodes);
    menu.panel.classList.remove("is-confirming");
    menu.pending = null;
  }

  function positionMenu(menu) {
    var wasLocked = menu.scrollLocked;
    var panel = menu.panel;
    var triggerRect = menu.trigger.getBoundingClientRect();
    var viewportWidth = Math.max(document.documentElement.clientWidth, window.innerWidth || 0);
    var viewportHeight = Math.max(document.documentElement.clientHeight, window.innerHeight || 0);
    var margin = 8;
    var rtl = document.documentElement.getAttribute("dir") === "rtl";

    panel.classList.remove("is-sheet", "is-side-sheet");
    panel.style.position = "fixed";
    panel.style.zIndex = "1001";
    panel.style.visibility = "hidden";
    panel.style.left = "0px";
    panel.style.right = "auto";
    panel.style.top = "0px";
    panel.style.bottom = "auto";
    panel.style.maxWidth = Math.max(0, viewportWidth - margin * 2) + "px";
    // On desktop, long filters stay in a scrollable, width-bounded popover
    // instead of becoming a viewport-wide sheet. Narrow screens use a sheet.
    var maxPanelHeight = Math.max(120, Math.min(viewportHeight - margin * 2, viewportHeight * 0.72));
    panel.style.maxHeight = maxPanelHeight + "px";
    panel.style.overflowY = "auto";

    var measured = panel.getBoundingClientRect();
    var panelWidth = Math.min(
      measured.width || panel.offsetWidth || 240,
      Math.max(0, viewportWidth - margin * 2)
    );
    var useSheet = viewportWidth <= 480;
    var panelHeight = 0;
    if (!useSheet) {
      // Measure the panel's NATURAL width before constraining it. Squeezing
      // the panel down to the gap left beside its trigger (the old
      // `anchoredWidth` clamp) is what clipped the changelist row menu to
      // «وی / چا / حذ»: the box really was ~40px wide, so the Persian
      // labels had nowhere to go. A menu may be narrower than it would
      // like, never narrower than its longest label.
      panel.style.minWidth = "0px";
      panel.style.width = "auto";
      var natural = Math.max(
        panel.getBoundingClientRect().width,
        panel.scrollWidth || 0
      );
      panelWidth = Math.min(
        natural || 220,
        Math.max(120, viewportWidth - margin * 2)
      );
      panel.style.width = panelWidth + "px";
      panelHeight = Math.min(panel.getBoundingClientRect().height, maxPanelHeight);
    }
    var below = viewportHeight - triggerRect.bottom - margin;
    var above = triggerRect.top - margin;

    if (useSheet) {
      panel.classList.add("is-sheet");
      if (menu.root.classList.contains("cusin-filter-menu")) {
        // Filters use a full-height side sheet on phones, aligned to the
        // filter trigger's RTL start edge instead of a generic bottom tray.
        panel.classList.add("is-side-sheet");
        var sheetWidth = Math.min(panelWidth, Math.max(0, viewportWidth - margin * 2));
        panel.style.left = rtl ? "auto" : margin + "px";
        panel.style.right = rtl ? margin + "px" : "auto";
        panel.style.top = margin + "px";
        panel.style.bottom = margin + "px";
        panel.style.width = sheetWidth + "px";
        panel.style.maxWidth = sheetWidth + "px";
        panel.style.maxHeight = Math.max(120, viewportHeight - margin * 2) + "px";
      } else {
        panel.style.left = margin + "px";
        panel.style.right = margin + "px";
        panel.style.top = "auto";
        panel.style.bottom = margin + "px";
        panel.style.width = "auto";
        panel.style.maxWidth = "none";
        panel.style.maxHeight = Math.max(120, Math.min(viewportHeight - margin * 2, viewportHeight * 0.72)) + "px";
      }
      menu.scrollLocked = true;
      if (!wasLocked) lockBodyScroll();
    } else {
      /* Preferred side: aligned to the trigger's RTL start edge (so in RTL
         it opens leftward, matching how the menu reads). When that side has
         no room -- the «کارها» column sits at the far left in RTL and its
         menu used to be pushed off-screen -- FLIP to the trigger's other
         side instead of shrinking or overflowing. */
      var startRoom = rtl
        ? triggerRect.right - margin
        : viewportWidth - triggerRect.left - margin;
      var endRoom = rtl
        ? viewportWidth - triggerRect.right - margin
        : triggerRect.left - margin;
      var useStartSide = startRoom >= panelWidth || startRoom >= endRoom;
      var left;
      if (rtl) {
        left = useStartSide ? triggerRect.right - panelWidth : triggerRect.left;
      } else {
        left = useStartSide ? triggerRect.left : triggerRect.right - panelWidth;
      }
      var top = triggerRect.bottom + 6;
      if (top + panelHeight > viewportHeight - margin && triggerRect.top - panelHeight - 6 >= margin) {
        top = triggerRect.top - panelHeight - 6;
      }
      // Last resort: keep it inside the viewport whatever happened above.
      left = Math.max(margin, Math.min(left, viewportWidth - panelWidth - margin));
      top = Math.max(margin, Math.min(top, viewportHeight - panelHeight - margin));
      panel.style.left = left + "px";
      panel.style.top = top + "px";
      panel.style.width = panelWidth + "px";
      menu.scrollLocked = false;
      if (wasLocked) unlockBodyScroll();
    }
    panel.style.visibility = "visible";
  }

  function closeMenu(restoreFocus) {
    if (!activeMenu) return;
    var menu = activeMenu;
    restoreConfirmation(menu);
    menu.panel.hidden = true;
    menu.panel.classList.remove("is-sheet", "is-side-sheet", "is-confirming");
    menu.panel.removeAttribute("style");
    if (menu.placeholder && menu.placeholder.parentNode) {
      menu.placeholder.parentNode.insertBefore(menu.panel, menu.placeholder);
      menu.placeholder.parentNode.removeChild(menu.placeholder);
    }
    menu.trigger.setAttribute("aria-expanded", "false");
    menu.root.classList.remove("is-open");
    if (menu.scrollLocked) unlockBodyScroll();
    activeMenu = null;
    if (restoreFocus && menu.trigger.isConnected) menu.trigger.focus();
  }

  function openMenu(root, focusLast) {
    if (activeMenu && activeMenu.root === root) {
      closeMenu(true);
      return;
    }
    if (activeMenu) closeMenu(false);
    var trigger = root.querySelector("[data-cusin-menu-trigger]");
    var panel = root.querySelector("[data-cusin-menu-panel]");
    if (!trigger || !panel) return;

    var placeholder = document.createComment("cusin-menu-panel");
    panel.parentNode.insertBefore(placeholder, panel);
    document.body.appendChild(panel);
    panel.hidden = false;
    trigger.setAttribute("aria-expanded", "true");
    root.classList.add("is-open");
    activeMenu = {
      root: root,
      trigger: trigger,
      panel: panel,
      placeholder: placeholder,
      pending: null,
      scrollLocked: false,
    };
    positionMenu(activeMenu);
    var items = getMenuItems(panel);
    if (items.length) items[focusLast ? items.length - 1 : 0].focus();
  }

  function submitAdminAction(form, submitter) {
    if (!form) return;
    if (typeof form.requestSubmit === "function") {
      form.requestSubmit(submitter || undefined);
      return;
    }
    var submitEvent = document.createEvent("Event");
    submitEvent.initEvent("submit", true, true);
    if (form.dispatchEvent(submitEvent) && typeof form.submit === "function") form.submit();
  }

  function runBulkAction(value, form, nativeSelects, submitter) {
    nativeSelects.forEach(function (select) {
      select.value = value;
      select.dispatchEvent(new Event("change", { bubbles: true }));
    });
    closeMenu(true);
    submitAdminAction(form, submitter);
  }

  function showConfirmation(menu, item, message) {
    var nodes = document.createDocumentFragment();
    while (menu.panel.firstChild) nodes.appendChild(menu.panel.firstChild);
    menu.pending = { item: item, nodes: nodes };
    menu.panel.classList.add("is-confirming");

    var question = document.createElement("p");
    question.className = "cusin-menu-confirm-message";
    question.setAttribute("role", "status");
    question.textContent = message;

    var actions = document.createElement("div");
    actions.className = "cusin-menu-confirm-actions";
    var cancel = document.createElement("button");
    cancel.type = "button";
    cancel.className = "cusin-menu-item";
    cancel.setAttribute("role", "menuitem");
    cancel.setAttribute("data-cusin-confirm-cancel", "");
    cancel.textContent = "بازگشت";
    var confirm = document.createElement("button");
    confirm.type = "button";
    confirm.className = "cusin-menu-item is-danger";
    confirm.setAttribute("role", "menuitem");
    confirm.setAttribute("data-cusin-confirm-yes", "");
    confirm.textContent = "بله، انجام شود";
    actions.appendChild(cancel);
    actions.appendChild(confirm);
    menu.panel.appendChild(question);
    menu.panel.appendChild(actions);
    confirm.focus();
  }

  function initMenus() {
    var menus = document.querySelectorAll("[data-cusin-menu]");
    menus.forEach(function (root) {
      var trigger = root.querySelector("[data-cusin-menu-trigger]");
      var panel = root.querySelector("[data-cusin-menu-panel]");
      if (!trigger || !panel || root.dataset.cusinMenuReady) return;
      root.dataset.cusinMenuReady = "true";
      if (!panel.id) panel.id = "cusin-menu-panel-auto-" + (++menuSequence);
      if (!trigger.id) trigger.id = "cusin-menu-trigger-auto-" + menuSequence;
      trigger.setAttribute("aria-haspopup", "menu");
      trigger.setAttribute("aria-controls", panel.id);
      trigger.setAttribute("aria-expanded", "false");
      panel.setAttribute("role", "menu");
      panel.setAttribute("aria-labelledby", trigger.id);
      panel.hidden = true;

      trigger.addEventListener("click", function (event) {
        event.preventDefault();
        openMenu(root, false);
      });
      trigger.addEventListener("keydown", function (event) {
        if (event.key === "ArrowDown" || event.key === "ArrowUp" ||
            event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          if (activeMenu && activeMenu.root === root) closeMenu(true);
          else openMenu(root, event.key === "ArrowUp");
        }
      });

      panel.addEventListener("click", function (event) {
        var cancel = event.target.closest && event.target.closest("[data-cusin-confirm-cancel]");
        if (cancel && activeMenu) {
          event.preventDefault();
          var pendingItem = activeMenu.pending && activeMenu.pending.item;
          restoreConfirmation(activeMenu);
          var previousItems = getMenuItems(panel);
          if (pendingItem && pendingItem.isConnected) pendingItem.focus();
          else if (previousItems.length) previousItems[0].focus();
          return;
        }
        var yes = event.target.closest && event.target.closest("[data-cusin-confirm-yes]");
        if (yes && activeMenu && activeMenu.pending) {
          event.preventDefault();
          var pending = activeMenu.pending;
          var actionItem = pending.item;
          restoreConfirmation(activeMenu);
          if (actionItem.hasAttribute("data-cusin-action-value")) {
            runBulkAction(
              actionItem.getAttribute("data-cusin-action-value"),
              actionItem._cusinForm,
              actionItem._cusinSelects,
              actionItem._cusinSubmitter
            );
          } else {
            actionItem.removeAttribute("data-cusin-confirm-message");
            var actionForm = actionItem.form || (actionItem.getAttribute("form") && document.getElementById(actionItem.getAttribute("form")));
            closeMenu(true);
            if (actionForm && actionItem.type === "submit") submitAdminAction(actionForm, actionItem);
            else if (actionItem.tagName === "A" && actionItem.href) window.location.href = actionItem.href;
            else actionItem.click();
          }
          return;
        }

        var item = event.target.closest && event.target.closest('[role="menuitem"], a[href], button:not([disabled])');
        if (!item) return;
        var bulkValue = item.getAttribute("data-cusin-action-value");
        if (bulkValue !== null) {
          event.preventDefault();
          if (item.hasAttribute("data-cusin-confirm-message")) {
            item._cusinForm = item._cusinForm || document.getElementById("changelist-form");
            item._cusinSelects = item._cusinSelects || Array.prototype.slice.call(
              document.querySelectorAll('#changelist-form select[name="action"]')
            );
            showConfirmation(activeMenu, item, item.getAttribute("data-cusin-confirm-message"));
          } else {
            runBulkAction(item.getAttribute("data-cusin-action-value"), item._cusinForm,
              item._cusinSelects || [], item._cusinSubmitter);
          }
          return;
        }
        if (item.hasAttribute("data-cusin-confirm-message")) {
          event.preventDefault();
          showConfirmation(activeMenu, item, item.getAttribute("data-cusin-confirm-message"));
          return;
        }
        closeMenu(true);
      });
    });

    document.addEventListener("click", function (event) {
      if (!activeMenu) return;
      var pendingItem = activeMenu.pending && activeMenu.pending.item;
      if (activeMenu.root.contains(event.target) || activeMenu.panel.contains(event.target) ||
          (pendingItem && (pendingItem === event.target || pendingItem.contains(event.target)))) return;
      // Let an outside control retain pointer/keyboard focus. Escape and
      // confirmation cancellation are the paths that explicitly return it.
      closeMenu(false);
    });
    document.addEventListener("keydown", function (event) {
      if (!activeMenu) return;
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopImmediatePropagation();
        closeMenu(true);
        return;
      }
      if (!activeMenu.panel.contains(event.target)) return;
      var items = getMenuItems(activeMenu.panel);
      if (!items.length) return;
      var current = items.indexOf(document.activeElement);
      if (event.key === "ArrowDown" || event.key === "ArrowUp" ||
          event.key === "Home" || event.key === "End") {
        event.preventDefault();
        var next = current;
        if (event.key === "Home") next = 0;
        else if (event.key === "End") next = items.length - 1;
        else if (event.key === "ArrowDown") next = (current + 1 + items.length) % items.length;
        else next = (current - 1 + items.length) % items.length;
        items[next].focus();
      }
    });
    window.addEventListener("resize", function () {
      if (activeMenu) positionMenu(activeMenu);
    });
    window.addEventListener("scroll", function () {
      if (activeMenu) positionMenu(activeMenu);
    }, true);
  }

  /* ------------------------------------------------------------------ *\
   * 2a. Sidebar: group state + scroll offset, per user, per browser tab
   * ------------------------------------------------------------------ */
  /* sessionStorage, not localStorage: which groups are expanded is "where
     I am right now", not a preference -- a shared shop computer must not
     inherit the previous user's layout, and a fresh tab should start
     clean. Every access is wrapped because privacy modes THROW on
     sessionStorage access, and a menu that breaks there is far worse
     than a menu that forgets. */
  function sidebarStore() {
    var store = null;
    try {
      store = window.sessionStorage;
    } catch (error) {
      store = null;
    }
    var userId = document.body.getAttribute("data-cusin-user-id") || "guest";
    var key = "cusin-admin-nav:v2:" + userId;
    return {
      read: function () {
        if (!store) return {};
        try {
          return JSON.parse(store.getItem(key) || "{}") || {};
        } catch (error) {
          return {};
        }
      },
      write: function (state) {
        if (!store) return;
        try {
          store.setItem(key, JSON.stringify(state));
        } catch (error) {
          /* quota or private mode: the menu still works, it just forgets */
        }
      }
    };
  }

  function initSidebarGroups() {
    var drawer = document.getElementById("cusin-drawer");
    var store = sidebarStore();
    var state = store.read();
    var openState = state.groups || {};
    var groups = document.querySelectorAll("#cusin-drawer [data-cusin-nav-group]");

    groups.forEach(function (group) {
      var id = group.getAttribute("data-cusin-nav-group");
      var summary = group.querySelector("summary");
      if (!summary) return;
      if (Object.prototype.hasOwnProperty.call(openState, id)) {
        group.open = Boolean(openState[id]);
      }
      summary.setAttribute("aria-expanded", group.open ? "true" : "false");
      group.addEventListener("toggle", function () {
        summary.setAttribute("aria-expanded", group.open ? "true" : "false");
        var current = store.read();
        current.groups = current.groups || {};
        current.groups[id] = group.open;
        store.write(current);
      });
    });

    if (!drawer) return;

    /* Remember WHERE the drawer was scrolled. Without this every save
       (a full page load) snapped the menu back to the top and the owner
       lost their place in a long list. */
    if (typeof state.scrollTop === "number" && state.scrollTop > 0) {
      drawer.scrollTop = state.scrollTop;
    }
    var scrollTimer = null;
    drawer.addEventListener("scroll", function () {
      if (scrollTimer) window.clearTimeout(scrollTimer);
      scrollTimer = window.setTimeout(function () {
        var current = store.read();
        current.scrollTop = drawer.scrollTop;
        store.write(current);
      }, 120);
    }, { passive: true });

    /* Bring the current row into view WITHOUT scrolling the page itself,
       and only when it is actually out of sight -- the menu must not
       jump under the cursor on every navigation. */
    var active = drawer.querySelector(
      ".cusin-nav-link.is-active, .cusin-nav-group.is-active > summary"
    );
    if (active && typeof active.scrollIntoView === "function") {
      try {
        active.scrollIntoView({ block: "nearest", inline: "nearest" });
      } catch (error) {
        /* old browsers: keep the default behaviour */
      }
    }
  }

  /* ------------------------------------------------------------------ *\
   * 2a-2. Header height -> --cusin-header-h (the drawer stays below it)
   * ------------------------------------------------------------------ */
  function initHeaderHeightVar() {
    var header = document.getElementById("header");
    var root = document.documentElement;
    if (!header || !root) return;
    var apply = function () {
      var height = Math.round(header.getBoundingClientRect().height);
      if (height > 0) root.style.setProperty("--cusin-header-h", height + "px");
    };
    apply();
    if (typeof window.ResizeObserver === "function") {
      new window.ResizeObserver(apply).observe(header);
    }
    window.addEventListener("resize", apply);
    /* Late-loading fonts change the topbar's height, and at 125%/150%
       zoom it wraps to two lines -- re-measure once they are in. */
    if (document.fonts && document.fonts.ready && typeof document.fonts.ready.then === "function") {
      document.fonts.ready.then(apply, function () {});
    }
  }

  /* ------------------------------------------------------------------ *\
   * 2c. Dashboard: period switcher + chart tooltip
   * ------------------------------------------------------------------ */
  /* The period is written to a cookie when a chip is clicked, so the next
     visit (or a reload without ?days=) opens on the same range. The
     cookie is per user id: two people on the same browser must not fight
     over it, and localStorage would not reach the server that renders the
     page -- which is what makes the first paint show the right range
     instead of flashing ۱۴ روز before correcting itself. */
  var DASH_COOKIE = "cusin_dash_days";

  /* Same per-user suffix the server uses (dashboard.period_cookie_name):
     the cookie the client writes is the cookie the server reads. */
  function dashCookieName() {
    var userId = document.body.getAttribute("data-cusin-user-id") || "guest";
    return DASH_COOKIE + "_" + userId;
  }

  function readCookie(name) {
    var parts = ("; " + document.cookie).split("; " + name + "=");
    if (parts.length < 2) return "";
    return decodeURIComponent(parts[1].split(";")[0]);
  }

  function initDashboardPeriod() {
    var chips = document.querySelectorAll("[data-cusin-period]");
    if (!chips.length) return;
    var cookieName = dashCookieName();
    var current = readCookie(cookieName);
    chips.forEach(function (chip) {
      chip.addEventListener("click", function () {
        var days = chip.getAttribute("data-cusin-period");
        if (!days) return;
        document.cookie =
          cookieName + "=" + encodeURIComponent(days) +
          "; path=/; max-age=" + 60 * 60 * 24 * 365 + "; samesite=lax";
      });
      // The server already rendered the active chip from the same cookie;
      // this only keeps a stale client-side view honest.
      if (current && chip.getAttribute("data-cusin-period") === current) {
        chip.classList.add("is-active");
      }
    });
  }

  /* A bar's numbers on hover AND on tap. <title> alone never fires on
     touch, and the owner checks the shop from a phone more often than
     from a desk. */
  function initChartTooltip() {
    var chart = document.querySelector("[data-cusin-chart]");
    if (!chart) return;
    var scroll = chart.closest(".cusin-chart-scroll") || chart.parentNode;
    var tip = scroll.querySelector("[data-cusin-chart-tip]");
    if (!tip) return;

    var show = function (bar) {
      var date = bar.getAttribute("data-date") || "";
      var amount = bar.getAttribute("data-amount") || "";
      var orders = bar.getAttribute("data-orders") || "0";
      tip.innerHTML = "";
      var head = document.createElement("span");
      head.textContent = date;
      var value = document.createElement("b");
      value.textContent = amount;
      var tail = document.createElement("span");
      tail.textContent = " — " + orders + " سفارش";
      tip.appendChild(head);
      tip.appendChild(document.createElement("br"));
      tip.appendChild(value);
      tip.appendChild(tail);
      tip.hidden = false;

      var scrollRect = scroll.getBoundingClientRect();
      var barRect = bar.getBoundingClientRect();
      var x = barRect.left - scrollRect.left + scroll.scrollLeft + barRect.width / 2;
      var y = barRect.top - scrollRect.top;
      tip.style.left = Math.max(0, x) + "px";
      tip.style.top = Math.max(0, y - 8) + "px";
    };
    var hide = function () {
      tip.hidden = true;
    };

    chart.addEventListener("mouseover", function (event) {
      var bar = event.target.closest && event.target.closest("[data-cusin-chart-bar]");
      if (bar) show(bar);
    });
    chart.addEventListener("mouseout", function (event) {
      if (event.target.closest && event.target.closest("[data-cusin-chart-bar]")) hide();
    });
    chart.addEventListener("click", function (event) {
      var bar = event.target.closest && event.target.closest("[data-cusin-chart-bar]");
      if (bar) show(bar);
    });
    // Touch: a tap anywhere else dismisses it.
    document.addEventListener("touchstart", function (event) {
      if (!tip.hidden && !(event.target.closest && event.target.closest("[data-cusin-chart]"))) {
        hide();
      }
    }, { passive: true });
    scroll.addEventListener("scroll", hide, { passive: true });
  }

  /* ------------------------------------------------------------------ *
   * 2b. Changelist toolbar, filter/date/sort and pagination menus
   * ------------------------------------------------------------------ */
  function addMenuItem(panel, text, href, icon, confirmMessage) {
    var item = document.createElement("a");
    item.href = href;
    item.className = "cusin-menu-item";
    item.setAttribute("role", "menuitem");
    if (icon) item.appendChild(spriteIcon(icon));
    var label = document.createElement("span");
    label.textContent = text;
    item.appendChild(label);
    if (confirmMessage) item.setAttribute("data-cusin-confirm-message", confirmMessage);
    panel.appendChild(item);
    return item;
  }

  function initBulkActionMenus() {
    var form = document.getElementById("changelist-form");
    if (!form) return;
    var allSelects = Array.prototype.slice.call(form.querySelectorAll('select[name="action"]'));
    if (!allSelects.length) return;
    var sourceSelect = allSelects[0];
    var options = Array.prototype.filter.call(sourceSelect.options, function (option) {
      return option.value && !option.disabled;
    });
    if (!options.length) return;

    allSelects.forEach(function (select) {
      select.classList.add("cusin-native-action-select");
      select.tabIndex = -1;
      select.setAttribute("aria-hidden", "true");
    });
    var submitter = form.querySelector('button[name="index"], input[name="index"]');
    if (!submitter) {
      submitter = document.createElement("button");
      submitter.type = "submit";
      submitter.name = "index";
      submitter.value = "0";
      submitter.setAttribute("hidden", "");
      form.appendChild(submitter);
    }
    submitter.setAttribute("hidden", "");

    form.querySelectorAll(".actions").forEach(function (actions, index) {
      if (actions.dataset.cusinActionsReady) return;
      actions.dataset.cusinActionsReady = "true";
      var menu = makeMenu("اقدام", "bulk-actions-" + index, "list", "cusin-bulk-menu");
      menu.trigger.setAttribute("aria-label", "اقدام برای موارد انتخاب‌شده");
      options.forEach(function (option) {
        var item = document.createElement("button");
        item.type = "button";
        item.className = "cusin-menu-item";
        item.setAttribute("role", "menuitem");
        item.setAttribute("data-cusin-action-value", option.value);
        item.textContent = option.textContent.trim();
        item._cusinForm = form;
        item._cusinSelects = allSelects;
        item._cusinSubmitter = submitter;
        if (/delete|remove|destroy/i.test(option.value)) {
          item.setAttribute("data-cusin-confirm-message",
            "آیا از انجام «" + option.textContent.trim() + "» روی موارد انتخاب‌شده مطمئن هستید؟");
          item.classList.add("is-danger");
        }
        menu.panel.appendChild(item);
      });
      actions.insertBefore(menu.root, actions.firstChild);
      var oldGo = actions.querySelector('button[name="index"], input[name="index"]');
      if (oldGo && oldGo !== submitter) oldGo.setAttribute("hidden", "");
    });
  }

  function stripLeadingArrows(text) {
    return String(text || "")
      .replace(/^[\s\u200e\u200f]*[‹›←→↔]+[\s\u200e\u200f]*/, "")
      .trim();
  }

  function clearFilterUrl() {
    var current = new URL(window.location.href);
    var keep = new URLSearchParams();
    ["q", "o", "ot"].forEach(function (key) {
      current.searchParams.getAll(key).forEach(function (value) {
        keep.append(key, value);
      });
    });
    var query = keep.toString();
    return current.pathname + (query ? "?" + query : "");
  }

  function initChangelistToolbar() {
    var changelist = document.getElementById("changelist");
    if (!changelist || changelist.dataset.cusinToolbarReady) return;
    changelist.dataset.cusinToolbarReady = "true";
    var container = changelist.querySelector(".changelist-form-container") || changelist;
    var toolbar = document.createElement("div");
    toolbar.className = "cusin-changelist-toolbar";
    toolbar.setAttribute("aria-label", "ابزارهای فهرست");
    container.insertBefore(toolbar, container.firstChild);

    var search = document.getElementById("toolbar");
    if (search) toolbar.appendChild(search);

    var dateNav = changelist.querySelector("nav.toplinks");
    if (dateNav) {
      var dateLinks = Array.prototype.slice.call(dateNav.querySelectorAll("a[href]"));
      if (dateLinks.length) {
        var dateMenu = makeMenu("بازهٔ زمانی", "date-range", "calendar", "cusin-date-menu");
        dateLinks.forEach(function (link) {
          var label = stripLeadingArrows(link.textContent);
          if (label) addMenuItem(dateMenu.panel, label, link.href, "calendar");
        });
        toolbar.appendChild(dateMenu.root);
      }
      dateNav.remove();
    }

    var filterNav = document.getElementById("changelist-filter");
    if (filterNav) {
      var filterMenu = makeMenu("فیلتر", "filters", "filter", "cusin-filter-menu");
      filterMenu.panel.classList.add("cusin-filter-panel");
      var extraActions = filterNav.querySelector("#changelist-filter-extra-actions");
      if (extraActions) extraActions.remove();

      var chips = document.createElement("div");
      chips.className = "cusin-active-filters";
      chips.setAttribute("aria-label", "فیلترهای فعال");
      var isResetChoice = function (text) {
        return /^(?:همه(?:\s+موارد)?|هر تاریخی|all)$/i.test(text.trim());
      };
      filterNav.querySelectorAll("details[data-filter-title]").forEach(function (details) {
        var selected = details.querySelector("li.selected a");
        if (!selected) return;
        var label = stripLeadingArrows(selected.textContent);
        if (!label || isResetChoice(label)) return;
        var remove = Array.prototype.slice.call(details.querySelectorAll("li a")).find(function (link) {
          return isResetChoice(link.textContent.trim());
        });
        if (remove) {
          var chip = document.createElement("a");
          chip.className = "cusin-filter-chip";
          chip.href = remove.href;
          chip.setAttribute("aria-label", "حذف فیلتر " + label);
          chip.textContent = label;
          chip.appendChild(spriteIcon("x"));
          chips.appendChild(chip);
        }
      });
      filterMenu.panel.appendChild(filterNav);
      toolbar.appendChild(filterMenu.root);
      if (chips.childElementCount) {
        var clearAll = document.createElement("a");
        clearAll.className = "cusin-filter-chip cusin-filter-chip--clear";
        clearAll.href = clearFilterUrl();
        clearAll.setAttribute("aria-label", "حذف همهٔ فیلترها");
        clearAll.textContent = "حذف همهٔ فیلترها";
        clearAll.appendChild(spriteIcon("x"));
        chips.insertBefore(clearAll, chips.firstChild);
        toolbar.appendChild(chips);
      }
    }

    var sortHeaders = document.querySelectorAll("#result_list thead th .text a[href]");
    if (sortHeaders.length) {
      var sortMenu = makeMenu("مرتب‌سازی", "sort", "sliders", "cusin-sort-menu");
      Array.prototype.forEach.call(sortHeaders, function (link) {
        addMenuItem(sortMenu.panel, link.textContent.trim(), link.href, "sliders");
      });
      toolbar.appendChild(sortMenu.root);
    }

    initBulkActionMenus();
    initRowActionMenus();
    initPaginationMenu();
  }

  function initRowActionMenus() {
    var table = document.getElementById("result_list");
    if (!table || table.dataset.cusinRowActionsReady) return;
    table.dataset.cusinRowActionsReady = "true";
    var headerRow = table.querySelector("thead tr");
    if (!headerRow) return;
    var actionHeader = document.createElement("th");
    actionHeader.scope = "col";
    actionHeader.className = "column-cusin-row-actions";
    actionHeader.textContent = "کارها";
    headerRow.appendChild(actionHeader);

    var deleteAllowed = !!document.querySelector('#changelist-form select[name="action"] option[value="delete_selected"]');
    table.querySelectorAll("tbody tr").forEach(function (row, index) {
      if (row.querySelector("[data-cusin-row-actions]")) return;
      var editLink = Array.prototype.slice.call(row.querySelectorAll('th a[href], td a[href]')).find(function (link) {
        return /\/change\/?(?:\?.*)?$/.test(link.getAttribute("href") || "");
      });
      var cell = document.createElement("td");
      cell.className = "cusin-row-actions";
      cell.setAttribute("data-label", "کارها");
      cell.setAttribute("data-cusin-row-actions", "");
      if (!editLink) {
        row.appendChild(cell);
        return;
      }
      var editUrl = editLink.href;
      var edit = document.createElement("a");
      edit.className = "cusin-row-edit";
      edit.href = editUrl;
      edit.title = "ویرایش";
      edit.setAttribute("aria-label", "ویرایش");
      edit.appendChild(spriteIcon("pencil"));
      cell.appendChild(edit);

      var menu = makeMenu("", "row-actions-" + index, "more", "cusin-row-menu");
      menu.trigger.classList.add("cusin-row-more");
      menu.trigger.setAttribute("aria-label", "کارهای بیشتر برای " + (editLink.textContent.trim() || "این مورد"));
      menu.trigger.title = "کارهای بیشتر";
      addMenuItem(menu.panel, "ویرایش", editUrl, "pencil");
      var storeData = row.querySelector("[data-cusin-store-url]");
      if (storeData && storeData.getAttribute("data-cusin-store-url")) {
        addMenuItem(menu.panel, "مشاهده در فروشگاه", storeData.getAttribute("data-cusin-store-url"), "external-link");
      }
      if (/\/orders\/order\//.test(editUrl)) {
        addMenuItem(menu.panel, "چاپ سفارش", editUrl.replace(/\/change\/?(?:\?.*)?$/, "/print/"), "printer");
      }
      if (deleteAllowed) {
        var deleteLink = addMenuItem(
          menu.panel,
          "حذف",
          editUrl.replace(/\/change\/?(?:\?.*)?$/, "/delete/"),
          "x",
          "آیا از حذف این مورد مطمئن هستید؟"
        );
        deleteLink.classList.add("is-danger");
      }
      cell.appendChild(menu.root);
      row.appendChild(cell);
    });
  }

  function initPaginationMenu() {
    document.querySelectorAll(".paginator").forEach(function (paginator, index) {
      if (paginator.dataset.cusinPaginationReady) return;
      var pageLinks = Array.prototype.slice.call(paginator.querySelectorAll("a:not(.showall)[href]"));
      var current = paginator.querySelector(".this-page");
      if (!pageLinks.length) return;
      paginator.dataset.cusinPaginationReady = "true";
      // The page numbers arrive from the server already Persian-ised; be
      // defensive for a template rendered without the filter.
      var currentLabel = current
        ? persianDigits(current.textContent.trim())
        : "۱";
      var menu = makeMenu("صفحهٔ " + currentLabel, "pagination-" + index, "chevron-down", "cusin-pagination-menu");
      pageLinks.forEach(function (link) {
        var item = addMenuItem(menu.panel, link.textContent.trim(), link.href, null);
        if (current && item.textContent.trim() === currentLabel) item.setAttribute("aria-current", "page");
      });
      paginator.insertBefore(menu.root, paginator.firstChild);
      paginator.classList.add("cusin-enhanced-pagination");
    });
  }

  /* ------------------------------------------------------------------ *
   * 2c. Persian tooltips and sprite icons for related-object controls
   * ------------------------------------------------------------------ */
  function initRelatedControls() {
    var labels = {
      "add-related": ["افزودن مورد تازه", "plus"],
      "change-related": ["ویرایش مورد", "pencil"],
      "view-related": ["مشاهدهٔ مورد", "eye"],
      "delete-related": ["حذف مورد", "x"],
    };
    document.querySelectorAll(".related-widget-wrapper-link").forEach(function (link) {
      var kind = Object.keys(labels).find(function (name) { return link.classList.contains(name); });
      if (!kind) return;
      var config = labels[kind];
      link.title = config[0];
      link.setAttribute("aria-label", config[0]);
      link.setAttribute("role", "button");
      link.replaceChildren(spriteIcon(config[1]));
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
    var tableSelector = "#result_list, .cusin-items-table, .inline-group .tabular table";
    function labelTables(root) {
      var tables = [];
      if (root.matches && root.matches(tableSelector)) tables.push(root);
      if (root.querySelectorAll) {
        tables = tables.concat(Array.prototype.slice.call(root.querySelectorAll(tableSelector)));
      }
      tables.forEach(function (table) {
        var headers = Array.prototype.map.call(
          table.querySelectorAll("thead th"),
          function (th) { return th.textContent.trim(); }
        );
        table.querySelectorAll("tbody tr").forEach(function (tr) {
          Array.prototype.forEach.call(tr.children, function (cell, index) {
            var label = headers[index];
            if (!label && cell.classList.contains("delete")) label = "حذف";
            if (!cell.hasAttribute("data-label") && label) {
              cell.setAttribute("data-label", label);
            }
          });
        });
      });
    }
    labelTables(document);

    // Django adds tabular inline rows after this script has initialized. A
    // small scoped observer labels those cloned cells as soon as they enter
    // the DOM, keeping the phone-card labels in sync with the table header.
    var content = document.querySelector("#content-main");
    if (content && "MutationObserver" in window) {
      var observer = new MutationObserver(function (records) {
        var inlineRowAdded = records.some(function (record) {
          return Array.prototype.some.call(record.addedNodes, function (node) {
            return node.nodeType === 1 && (
              (node.matches && node.matches(".inline-group .tabular tr")) ||
              (node.closest && node.closest(".inline-group .tabular"))
            );
          });
        });
        if (inlineRowAdded) labelTables(content);
      });
      observer.observe(content, { childList: true, subtree: true });
    }
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
   * 6b. Persian digits in Django's own chrome
   *
   * Django counts in ASCII: «0 از 1 انتخاب شده‌اند»، «صفحهٔ 1»، «165
   * محصولات». The server-rendered ones are fixed in the overridden
   * admin/actions.html, admin/pagination.html and admin/search_form.html;
   * this handles the two that Django's own JavaScript rewrites AFTER the
   * page has loaded (the action counter and the pagination menu label),
   * because there is no hook to intercept them.
   * ------------------------------------------------------------------ */
  var PERSIAN_DIGITS = ["\u06f0", "\u06f1", "\u06f2", "\u06f3", "\u06f4",
    "\u06f5", "\u06f6", "\u06f7", "\u06f8", "\u06f9"];

  function persianDigits(text) {
    if (!text) return text;
    return String(text).replace(/[0-9]/g, function (digit) {
      return PERSIAN_DIGITS[Number(digit)];
    });
  }

  function persianDigitsIn(node) {
    if (!node || node.dataset.cusinDigitsDone === "true") return;
    var next = persianDigits(node.textContent);
    if (next !== node.textContent) {
      // Only ever touch the text: the counter also carries
      // data-attributes that Django's actions.js reads back.
      node.textContent = next;
    }
    node.dataset.cusinDigitsDone = "true";
  }

  function initPersianDigits() {
    var nodes = document.querySelectorAll(".action-counter, .all, .question");
    if (!nodes.length) return;
    nodes.forEach(persianDigitsIn);
    // Django's actions.js replaces the counter's text on every checkbox
    // change, so re-run whenever it does.
    if (typeof MutationObserver !== "function") return;
    nodes.forEach(function (node) {
      var observer = new MutationObserver(function () {
        node.dataset.cusinDigitsDone = "false";
        persianDigitsIn(node);
      });
      observer.observe(node, { childList: true, characterData: true, subtree: true });
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
    initHeaderHeightVar();
    initSidebarGroups();
    initDashboardPeriod();
    initChartTooltip();
    initChangelistToolbar();
    initRelatedControls();
    initCardLabels();
    initMenus();
    initPalette();
    initCopyButtons();
    initQuickStatusGuard();
    initPersianDigits();
    initMisc();
  });
})();
