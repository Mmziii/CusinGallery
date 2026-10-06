/**
 * Tiny toast bus (Part 3, extended in Part S2 item 6): any module calls
 * toast("…") and the single <Toaster /> mounted in MainLayout shows it.
 * No dependency added -- a CustomEvent is plenty for cart/wishlist
 * feedback. An optional ACTION ({label, to}) renders as a router link
 * inside the toast (e.g. «مشاهده سبد» after add-to-cart).
 */
export function toast(message, kind = "success", action = null) {
  window.dispatchEvent(
    new CustomEvent("cusin:toast", { detail: { message, kind, action } })
  );
}

export function onToast(handler) {
  const listener = (event) => handler(event.detail);
  window.addEventListener("cusin:toast", listener);
  return () => window.removeEventListener("cusin:toast", listener);
}
