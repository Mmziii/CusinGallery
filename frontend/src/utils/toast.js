/**
 * Tiny toast bus (Part 3): any module calls toast("…") and the single
 * <Toaster /> mounted in MainLayout shows it. No dependency added --
 * a CustomEvent is plenty for cart/wishlist feedback.
 */
export function toast(message, kind = "success") {
  window.dispatchEvent(new CustomEvent("cusin:toast", { detail: { message, kind } }));
}

export function onToast(handler) {
  const listener = (event) => handler(event.detail);
  window.addEventListener("cusin:toast", listener);
  return () => window.removeEventListener("cusin:toast", listener);
}
