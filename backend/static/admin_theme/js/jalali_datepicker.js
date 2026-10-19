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
    button.textContent = "▦";
    wrap.appendChild(button);
    const popup = document.createElement("div");
    popup.className = "jalali-date-picker";
    popup.hidden = true;
    popup.setAttribute("role", "dialog");
    popup.setAttribute("aria-label", "انتخاب تاریخ جلالی");
    wrap.appendChild(popup);

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
          popup.hidden = true;
          input.focus();
        });
        days.appendChild(choice);
      }
      popup.append(head, days);
    };
    render();
    button.addEventListener("click", () => { popup.hidden = !popup.hidden; if (!popup.hidden) render(); });
    document.addEventListener("click", event => { if (!wrap.contains(event.target)) popup.hidden = true; });
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
