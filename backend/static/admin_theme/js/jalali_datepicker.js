(() => {
  "use strict";
  const months = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور", "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"];
  const fa = value => String(value).replace(/\d/g, d => "۰۱۲۳۴۵۶۷۸۹"[Number(d)]);
  const latin = value => String(value).replace(/[۰-۹٠-٩]/g, d => String(d.charCodeAt(0) >= 0x06f0 && d.charCodeAt(0) <= 0x06f9 ? d.charCodeAt(0) - 0x06f0 : d.charCodeAt(0) - 0x0660));
  const currentJalali = () => {
    const parts = new Intl.DateTimeFormat("en-u-ca-persian", { year: "numeric", month: "numeric", day: "numeric" }).formatToParts(new Date());
    const get = type => Number(parts.find(part => part.type === type)?.value || 1);
    return { year: get("year"), month: get("month"), day: get("day") };
  };
  const jalaliNewYear = year => {
    const formatter = new Intl.DateTimeFormat("en-u-ca-persian", { timeZone: "UTC", year: "numeric", month: "numeric", day: "numeric" });
    for (let offset = 18; offset <= 22; offset++) {
      const date = new Date(Date.UTC(year + 621, 2, offset));
      const parts = formatter.formatToParts(date);
      const get = type => Number(parts.find(part => part.type === type)?.value || 0);
      if (get("year") === year && get("month") === 1 && get("day") === 1) return date;
    }
    return new Date(Date.UTC(year + 621, 2, 21));
  };
  const daysInMonth = (year, month) => {
    if (month <= 6) return 31;
    if (month <= 11) return 30;
    return (jalaliNewYear(year + 1) - jalaliNewYear(year)) / 86400000 === 366 ? 30 : 29;
  }; 

  const initialized = new WeakSet();
  let pickerSequence = 0;
  const initialize = (root = document) => {
    const fields = [];
    if (root.matches?.('input[data-jalali-date="true"]')) fields.push(root);
    fields.push(...root.querySelectorAll('input[data-jalali-date="true"]'));
    fields.forEach(input => {
    if (initialized.has(input) || !input.parentNode) return;
    initialized.add(input);
    // Django inline formsets clone the already-rendered empty form. If the
    // source input was decorated, cloned controls have no listeners; unwrap
    // them and rebuild the widget for this new input node.
    const oldWrap = input.closest(".jalali-date-wrap");
    if (oldWrap) {
      oldWrap.parentNode.insertBefore(input, oldWrap);
      oldWrap.remove();
    }
    const wrap = document.createElement("span");
    wrap.className = "jalali-date-wrap";
    input.parentNode.insertBefore(wrap, input);
    wrap.appendChild(input);
    const button = document.createElement("button");
    button.type = "button";
    button.className = "jalali-date-open";
    button.setAttribute("aria-label", "بازکردن تقویم جلالی");
    button.setAttribute("aria-expanded", "false");
    const calendarIcon = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    calendarIcon.setAttribute("class", "cusin-icon jalali-date-open__icon");
    calendarIcon.setAttribute("aria-hidden", "true");
    calendarIcon.setAttribute("focusable", "false");
    const calendarUse = document.createElementNS("http://www.w3.org/2000/svg", "use");
    calendarUse.setAttribute("href", "#cusin-i-calendar");
    calendarIcon.appendChild(calendarUse);
    button.appendChild(calendarIcon);
    wrap.appendChild(button);
    const popup = document.createElement("div");
    popup.className = "jalali-date-picker";
    popup.id = `jalali-date-picker-${++pickerSequence}`;
    button.setAttribute("aria-controls", popup.id);
    popup.hidden = true;
    popup.setAttribute("role", "dialog");
    popup.setAttribute("aria-label", "انتخاب تاریخ جلالی");
    document.body.appendChild(popup);

    const initial = currentJalali();
    let year = initial.year;
    let month = initial.month;
    const existing = latin(input.value).match(/(\d{3,4})[/-](\d{1,2})[/-](\d{1,2})/);
    if (existing) { year = Number(existing[1]); month = Number(existing[2]); }

    const render = () => {
      popup.replaceChildren();
      const head = document.createElement("div");
      head.className = "jalali-date-picker__head";
      const previous = document.createElement("button");
      previous.type = "button"; previous.textContent = "‹"; previous.setAttribute("aria-label", "ماه پیش");
      previous.addEventListener("click", () => { month--; if (month < 1) { month = 12; year--; } render(); });
      const select = document.createElement("select");
      months.forEach((name, index) => {
        const option = document.createElement("option"); option.value = String(index + 1); option.textContent = name; option.selected = index + 1 === month; select.appendChild(option);
      });
      select.addEventListener("change", () => { month = Number(select.value); render(); });
      const yearInput = document.createElement("input");
      yearInput.type = "number"; yearInput.min = "1300"; yearInput.max = "1599"; yearInput.value = String(year); yearInput.setAttribute("aria-label", "سال جلالی");
      yearInput.addEventListener("change", () => { year = Math.min(1599, Math.max(1300, Number(yearInput.value) || initial.year)); render(); });
      const next = document.createElement("button");
      next.type = "button"; next.textContent = "›"; next.setAttribute("aria-label", "ماه بعد");
      next.addEventListener("click", () => { month++; if (month > 12) { month = 1; year++; } render(); });
      head.append(previous, select, yearInput, next);
      const days = document.createElement("div"); days.className = "jalali-date-picker__days";
      for (let day = 1; day <= daysInMonth(year, month); day++) {
        const choice = document.createElement("button");
        choice.type = "button"; choice.textContent = fa(day); choice.setAttribute("aria-label", `${fa(year)}/${fa(String(month).padStart(2, "0"))}/${fa(String(day).padStart(2, "0"))}`);
        choice.addEventListener("click", () => {
          const time = latin(input.value).match(/\s+(\d{1,2}:\d{2}(?::\d{2})?)/)?.[1];
          input.value = `${fa(year)}/${fa(String(month).padStart(2, "0"))}/${fa(String(day).padStart(2, "0"))}${time ? ` ${fa(time)}` : ""}`;
          input.dispatchEvent(new Event("input", { bubbles: true }));
          input.dispatchEvent(new Event("change", { bubbles: true }));
          closePopup();
          input.focus();
        });
        days.appendChild(choice);
      }
      popup.append(head, days);
    };
    render();

    const repositionPopup = () => {
      if (popup.hidden) return;
      const viewportWidth = Math.max(document.documentElement.clientWidth, window.innerWidth || 0);
      const viewportHeight = Math.max(document.documentElement.clientHeight, window.innerHeight || 0);
      const margin = 8;
      const inputRect = input.getBoundingClientRect();
      const isPhone = viewportWidth <= 600;

      popup.style.position = "fixed";
      popup.style.zIndex = "1200";
      popup.style.visibility = "hidden";
      popup.style.maxWidth = `${Math.max(0, viewportWidth - margin * 2)}px`;
      popup.style.maxHeight = `${Math.max(120, viewportHeight - margin * 2)}px`;
      popup.style.overflowY = "auto";
      popup.classList.toggle("jalali-date-picker--mobile", isPhone);

      if (isPhone) {
        popup.style.left = `${margin}px`;
        popup.style.right = `${margin}px`;
        popup.style.top = "auto";
        popup.style.bottom = "8px";
        popup.style.width = "auto";
        popup.style.maxWidth = "none";
        popup.style.maxHeight = `${Math.max(120, Math.min(viewportHeight - margin * 2, viewportHeight * 0.72))}px`;
        popup.style.visibility = "visible";
        return;
      }

      popup.style.right = "auto";
      popup.style.bottom = "auto";
      popup.style.width = "280px";
      popup.style.left = "0px";
      popup.style.top = "0px";
      const measured = popup.getBoundingClientRect();
      const popupWidth = Math.min(measured.width || 280, Math.max(0, viewportWidth - margin * 2));
      const popupHeight = Math.min(measured.height || popup.scrollHeight || 340, viewportHeight - margin * 2);
      const below = viewportHeight - inputRect.bottom - margin;
      const above = inputRect.top - margin;
      const placeBelow = below >= popupHeight || (above < popupHeight && below >= above);
      let left = inputRect.right - popupWidth;
      let top = placeBelow ? inputRect.bottom + 4 : inputRect.top - popupHeight - 4;
      left = Math.max(margin, Math.min(left, viewportWidth - popupWidth - margin));
      top = Math.max(margin, Math.min(top, viewportHeight - popupHeight - margin));
      popup.style.width = `${popupWidth}px`;
      popup.style.left = `${left}px`;
      popup.style.top = `${top}px`;
      popup.style.visibility = "visible";
    };

    const closePopup = (restoreFocus = false) => {
      if (popup.hidden) return;
      popup.hidden = true;
      popup.classList.remove("jalali-date-picker--mobile");
      button.setAttribute("aria-expanded", "false");
      window.removeEventListener("scroll", repositionPopup, true);
      window.removeEventListener("resize", repositionPopup);
      if (restoreFocus) button.focus();
    };

    const openPopup = () => {
      popup.hidden = false;
      button.setAttribute("aria-expanded", "true");
      render();
      repositionPopup();
      window.addEventListener("scroll", repositionPopup, true);
      window.addEventListener("resize", repositionPopup);
    };

    button.addEventListener("click", () => {
      if (popup.hidden) openPopup();
      else closePopup();
    });
    document.addEventListener("click", event => {
      if (!wrap.contains(event.target) && !popup.contains(event.target)) closePopup();
    });
    document.addEventListener("keydown", event => {
      if (!popup.hidden && event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        closePopup(true);
      }
    });
    });
  };

  const start = () => {
    initialize();
    new MutationObserver(records => {
      records.forEach(record => record.addedNodes.forEach(node => {
        if (node.nodeType === 1) initialize(node);
      }));
    }).observe(document.documentElement, { childList: true, subtree: true });
  };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, { once: true });
  else start();
})();
