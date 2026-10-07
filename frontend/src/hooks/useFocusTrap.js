import { useEffect, useRef, useState } from "react";

/**
 * Part S2 item 8: keyboard support for drawers/dialogs. While `active`,
 * focus is moved into the container, Tab/Shift+Tab cycle inside it,
 * Escape calls `onClose`, and on deactivation focus returns to the
 * element that opened the surface (focus restore).
 *
 * Part S5 follow-up 4 hardening (the drawers became portals): the opener
 * is remembered ONCE per activation and the latest `onClose` is read from
 * a ref, so a re-render while the surface is open (hydration finishing,
 * cart update, portal mounting one paint later) can neither re-run the
 * focus move nor replace the element that focus must return to. When the
 * container is not in the DOM yet the hook retries on the next task
 * instead of silently doing nothing.
 */
const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

export default function useFocusTrap(ref, active, onClose) {
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  const restoreRef = useRef(null);
  const [retry, setRetry] = useState(0);

  // The container can mount one paint after `active` flips (portal, lazy
  // render): retry once instead of leaving the surface without a trap.
  useEffect(() => {
    if (!active || ref.current) return undefined;
    const id = window.setTimeout(() => setRetry((n) => n + 1), 0);
    return () => window.clearTimeout(id);
  }, [active, ref, retry]);

  useEffect(() => {
    if (!active || !ref.current) return undefined;
    const container = ref.current;
    if (!restoreRef.current) {
      restoreRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    }

    const focusables = () =>
      [...container.querySelectorAll(FOCUSABLE)].filter(
        (el) => !el.hasAttribute("hidden") && el.getAttribute("aria-hidden") !== "true"
      );

    if (!container.contains(document.activeElement)) {
      const first = focusables()[0];
      if (first) first.focus();
    }

    function onKeyDown(event) {
      if (event.key === "Escape") {
        event.stopPropagation();
        if (onCloseRef.current) onCloseRef.current();
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
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [active, ref, retry]);

  // Focus restore, once, when the surface really closes.
  useEffect(() => {
    if (active) return undefined;
    const target = restoreRef.current;
    restoreRef.current = null;
    if (target && typeof target.focus === "function" && document.contains(target)) target.focus();
    return undefined;
  }, [active]);
}
