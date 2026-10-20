(() => {
  "use strict";
  const months = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور", "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"];
  const weekdays = ["ش", "ی", "د", "س", "چ", "پ", "ج"];
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

  const jalaliFirstDayWeekday = (year, month) => {
    const dayOffset = month <= 7 ? (month - 1) * 31 : 6 * 31 + (month - 7) * 30;
    const ny = jalaliNewYear(year);
    const d = new Date(ny.getTime() + dayOffset * 86400000);
    return (d.getUTCDay() + 1) % 7;
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

      // Remove any Django default DateTimeShortcuts sibling widgets
      const shortcuts = input.parentNode.querySelectorAll(".datetimeshortcuts, .calendar-shortcuts, .time-shortcuts");
      shortcuts.forEach(el => el.remove());

      // Django inline formsets clone the already-rendered empty form. If the
      // source input was decorated, cloned controls have no listeners; unwrap
      // them and rebuild the widget for this new input node.
      const oldWrap = input.closest(".jalali-date-wrap");
      if (oldWrap) {
        oldWrap.parentNode.insertBefore(input, oldWrap);
        oldWrap.remove();
      }

      const withTime = input.getAttribute("data-jalali-with-time") === "true";

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
      let selectedDay = null;
      let selectedHour = 0;
      let selectedMinute = 0;

      const parseCurrentValue = () => {
        const raw = latin(input.value || "");
        const dateMatch = raw.match(/(\d{3,4})[/-](\d{1,2})[/-](\d{1,2})/);
        if (dateMatch) {
          year = Number(dateMatch[1]);
          month = Number(dateMatch[2]);
          selectedDay = Number(dateMatch[3]);
        }
        const timeMatch = raw.match(/\s+(\d{1,2}):(\d{2})/);
        if (timeMatch) {
          selectedHour = Number(timeMatch[1]);
          selectedMinute = Number(timeMatch[2]);
        }
      };
      parseCurrentValue();

      const updateInputValue = (close = false) => {
        const d = selectedDay || initial.day;
        let text = `${fa(year)}/${fa(String(month).padStart(2, "0"))}/${fa(String(d).padStart(2, "0"))}`;
        if (withTime) {
          text += ` ${fa(String(selectedHour).padStart(2, "0"))}:${fa(String(selectedMinute).padStart(2, "0"))}`;
        }
        input.value = text;
        input.dispatchEvent(new Event("input", { bubbles: true }));
        input.dispatchEvent(new Event("change", { bubbles: true }));
        if (close) {
          closePopup(true);
        }
      };

      const render = () => {
        popup.replaceChildren();

        // 1. Header (month select + Persian year display/input + prev/next)
        const head = document.createElement("div");
        head.className = "jalali-date-picker__head";

        const previous = document.createElement("button");
        previous.type = "button";
        previous.textContent = "‹";
        previous.setAttribute("aria-label", "ماه پیش");
        previous.addEventListener("click", () => {
          month--;
          if (month < 1) { month = 12; year--; }
          render();
          repositionPopup();
        });

        const select = document.createElement("select");
        months.forEach((name, index) => {
          const option = document.createElement("option");
          option.value = String(index + 1);
          option.textContent = name;
          option.selected = index + 1 === month;
          select.appendChild(option);
        });
        select.addEventListener("change", () => {
          month = Number(select.value);
          render();
          repositionPopup();
        });

        const yearInput = document.createElement("input");
        yearInput.type = "text";
        yearInput.className = "jalali-date-picker__year";
        yearInput.inputMode = "numeric";
        yearInput.value = fa(year);
        yearInput.setAttribute("aria-label", "سال جلالی");
        yearInput.addEventListener("focus", () => { yearInput.select(); });
        yearInput.addEventListener("change", () => {
          const parsed = Number(latin(yearInput.value));
          year = Math.min(1599, Math.max(1300, parsed || initial.year));
          yearInput.value = fa(year);
          render();
          repositionPopup();
        });

        const next = document.createElement("button");
        next.type = "button";
        next.textContent = "›";
        next.setAttribute("aria-label", "ماه بعد");
        next.addEventListener("click", () => {
          month++;
          if (month > 12) { month = 1; year++; }
          render();
          repositionPopup();
        });

        head.append(previous, select, yearInput, next);

        // 2. Weekday headers: ش ی د س چ پ ج
        const weekdayRow = document.createElement("div");
        weekdayRow.className = "jalali-date-picker__weekdays";
        weekdays.forEach(dayLetter => {
          const wSpan = document.createElement("span");
          wSpan.className = "jalali-date-picker__weekday";
          wSpan.textContent = dayLetter;
          weekdayRow.appendChild(wSpan);
        });

        // 3. Days grid with weekday alignment
        const days = document.createElement("div");
        days.className = "jalali-date-picker__days";

        // Day of the week offset (0 = Saturday/ش)
        const firstDayOffset = jalaliFirstDayWeekday(year, month);
        for (let i = 0; i < firstDayOffset; i++) {
          const empty = document.createElement("span");
          empty.className = "jalali-date-picker__empty";
          empty.setAttribute("aria-hidden", "true");
          days.appendChild(empty);
        }

        const today = currentJalali();
        const numDays = daysInMonth(year, month);

        for (let day = 1; day <= numDays; day++) {
          const choice = document.createElement("button");
          choice.type = "button";
          choice.textContent = fa(day);
          choice.setAttribute("aria-label", `${fa(year)}/${fa(String(month).padStart(2, "0"))}/${fa(String(day).padStart(2, "0"))}`);

          // Highlight today
          if (today.year === year && today.month === month && today.day === day) {
            choice.classList.add("jalali-date-picker__day--today");
            choice.setAttribute("aria-current", "date");
          }

          // Highlight selected day
          if (selectedDay === day) {
            choice.classList.add("jalali-date-picker__day--selected");
          }

          choice.addEventListener("click", () => {
            selectedDay = day;
            if (withTime) {
              updateInputValue(false);
              render();
              repositionPopup();
            } else {
              updateInputValue(true);
            }
          });

          days.appendChild(choice);
        }

        popup.append(head, weekdayRow, days);

        // 4. Time selection (for fields that need a time component)
        if (withTime) {
          const timeWrap = document.createElement("div");
          timeWrap.className = "jalali-date-picker__time";

          const timeLabel = document.createElement("span");
          timeLabel.className = "jalali-date-picker__time-label";
          timeLabel.textContent = "زمان:";

          const hourSelect = document.createElement("select");
          hourSelect.className = "jalali-date-picker__time-select";
          hourSelect.setAttribute("aria-label", "ساعت");
          for (let h = 0; h < 24; h++) {
            const opt = document.createElement("option");
            opt.value = String(h);
            opt.textContent = fa(String(h).padStart(2, "0"));
            if (h === selectedHour) opt.selected = true;
            hourSelect.appendChild(opt);
          }
          hourSelect.addEventListener("change", () => {
            selectedHour = Number(hourSelect.value);
            updateInputValue(false);
          });

          const timeSep = document.createElement("span");
          timeSep.className = "jalali-date-picker__time-sep";
          timeSep.textContent = ":";

          const minSelect = document.createElement("select");
          minSelect.className = "jalali-date-picker__time-select";
          minSelect.setAttribute("aria-label", "دقیقه");
          for (let m = 0; m < 60; m++) {
            const opt = document.createElement("option");
            opt.value = String(m);
            opt.textContent = fa(String(m).padStart(2, "0"));
            if (m === selectedMinute) opt.selected = true;
            minSelect.appendChild(opt);
          }
          minSelect.addEventListener("change", () => {
            selectedMinute = Number(minSelect.value);
            updateInputValue(false);
          });

          const confirmBtn = document.createElement("button");
          confirmBtn.type = "button";
          confirmBtn.className = "jalali-date-picker__confirm";
          confirmBtn.textContent = "تأیید";
          confirmBtn.addEventListener("click", () => {
            updateInputValue(true);
          });

          // Clock order, not paragraph order: the row is LTR so the hour
          // select sits on the LEFT and the minute on the RIGHT («ساعت :
          // دقیقه»), while the «زمان:» label stays on the right edge.
          timeWrap.setAttribute("dir", "ltr");
          timeWrap.append(hourSelect, timeSep, minSelect, confirmBtn, timeLabel);
          popup.appendChild(timeWrap);
        }
      };

      const repositionPopup = () => {
        if (popup.hidden) return;
        const viewportWidth = Math.max(document.documentElement.clientWidth, window.innerWidth || 0);
        const viewportHeight = Math.max(document.documentElement.clientHeight, window.innerHeight || 0);
        const margin = 8;
        const inputRect = input.getBoundingClientRect();
        const isPhone = viewportWidth <= 600;

        if (isPhone) {
          popup.style.position = "fixed";
          popup.style.zIndex = "1200";
          popup.style.insetInline = `${margin}px`;
          popup.style.left = `${margin}px`;
          popup.style.right = `${margin}px`;
          popup.style.top = "auto";
          popup.style.bottom = "8px";
          popup.style.width = "auto";
          popup.style.maxWidth = "none";
          popup.style.maxHeight = `${Math.max(120, Math.min(viewportHeight - margin * 2, viewportHeight * 0.72))}px`;
          popup.classList.add("jalali-date-picker--mobile");
          popup.style.visibility = "visible";
          return;
        }

        popup.classList.remove("jalali-date-picker--mobile");
        popup.style.position = "fixed";
        popup.style.zIndex = "1200";
        popup.style.right = "auto";
        popup.style.bottom = "auto";
        popup.style.width = "290px";
        popup.style.left = "0px";
        popup.style.top = "0px";
        popup.style.visibility = "hidden";

        const measured = popup.getBoundingClientRect();
        const popupWidth = Math.min(measured.width || 290, Math.max(0, viewportWidth - margin * 2));
        const popupHeight = Math.min(measured.height || popup.scrollHeight || 360, viewportHeight - margin * 2);

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
        document.removeEventListener("scroll", repositionPopup, true);
        window.removeEventListener("resize", repositionPopup);
        if (restoreFocus) button.focus();
      };

      const openPopup = () => {
        parseCurrentValue();
        popup.hidden = false;
        button.setAttribute("aria-expanded", "true");
        render();
        repositionPopup();
        window.addEventListener("scroll", repositionPopup, true);
        document.addEventListener("scroll", repositionPopup, true);
        window.addEventListener("resize", repositionPopup);
      };

      button.addEventListener("click", () => {
        if (popup.hidden) openPopup();
        else closePopup();
      });

      document.addEventListener("click", event => {
        if (!wrap.contains(event.target) && !popup.contains(event.target)) {
          closePopup();
        }
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
