/**
 * Normalizes an Axios error from this project's DRF backend into one
 * consistent shape, since DRF itself returns different error bodies
 * depending on the situation:
 *   - 400 validation errors: {"quantity": ["Only 3 available for this item."]}
 *   - 403/404/permission errors: {"detail": "Not found."}
 *   - network failure / no response at all: no `error.response`
 *
 * Used by both useCartStore and useWishlist so UI code has one shape to
 * handle regardless of which of these actually happened, rather than
 * re-deriving this per call site.
 *
 * @returns {{status: number|null, message: string, fieldErrors: Object, isAuthError: boolean, isNetworkError: boolean}}
 */
export function normalizeApiError(error) {
  if (!error?.response) {
    return {
      status: null,
      message: "اتصال به سرور برقرار نشد. لطفاً اتصال اینترنت خود را بررسی کنید.",
      fieldErrors: {},
      isAuthError: false,
      isNetworkError: true,
    };
  }

  const { status, data } = error.response;
  const isAuthError = status === 401 || status === 403;

  if (isAuthError) {
    return {
      status,
      message: "لطفاً وارد حساب کاربری خود شوید.",
      fieldErrors: {},
      isAuthError: true,
      isNetworkError: false,
    };
  }

  if (status === 404) {
    return {
      status,
      message: data?.detail || "مورد درخواستی پیدا نشد.",
      fieldErrors: {},
      isAuthError: false,
      isNetworkError: false,
    };
  }

  // 400-style validation errors: {field: [messages]} or {detail: "..."}
  if (data && typeof data === "object") {
    if (typeof data.detail === "string") {
      return { status, message: data.detail, fieldErrors: {}, isAuthError: false, isNetworkError: false };
    }
    const fieldErrors = data;
    const firstMessage = Object.values(fieldErrors).flat().find((m) => typeof m === "string");
    return {
      status,
      message: firstMessage || "امکان انجام درخواست وجود ندارد. لطفاً ورودی‌ها را بررسی کنید.",
      fieldErrors,
      isAuthError: false,
      isNetworkError: false,
    };
  }

  return {
    status,
    message: "خطایی رخ داد. لطفاً دوباره تلاش کنید.",
    fieldErrors: {},
    isAuthError: false,
    isNetworkError: false,
  };
}
