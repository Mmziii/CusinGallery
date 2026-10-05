import { useEffect } from "react";

/**
 * Part S2 item 8: keyboard support for drawers/dialogs. While `active`,
 * focus is moved into the container, Tab/Shift+Tab cycle inside it,
 * Escape calls `onClose`, and on deactivation focus returns to the
 * element that opened the surface (focus restore).
 */
const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

export default function useFocusTrap(ref, active, onClose) {
  useEffect(() => {
    if (!active || !ref.current) return undefined;
    const container = ref.current;
    const previouslyFocused =
      document.activeElement instanceof HTMLElement ? document.activeElement : null;

    const focusables = () =>
      [...container.querySelectorAll(FOCUSABLE)].filter(
        (el) => !el.hasAttribute("hidden") && el.getAttribute("aria-hidden") !== "true"
      );

    const first = focusables()[0];
    if (first) first.focus();

    function onKeyDown(event) {
      if (event.key === "Escape") {
        event.stopPropagation();
        if (onClose) onClose();
        return;
      }
      if (event.key !== "Tab") return;
      const items = focusables();
      if (items.length === 0) {
        event.preventDefault();
        return;
      }
      const firstEl = items[0];
      const lastEl = items[items.length - 1];
      if (event.shiftKey && document.activeElement === firstEl) {
        event.preventDefault();
        lastEl.focus();
      } else if (!event.shiftKey && document.activeElement === lastEl) {
        event.preventDefault();
        firstEl.focus();
      }
    }

    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      // Focus restore: the trigger gets focus back when the surface closes.
      if (previouslyFocused && typeof previouslyFocused.focus === "function") {
        previouslyFocused.focus();
      }
    };
  }, [active, ref, onClose]);
}
