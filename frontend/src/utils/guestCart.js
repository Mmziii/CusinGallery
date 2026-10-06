/**
 * Guest cart persistence (Part 1). localStorage holds ONLY
 * {product_id, variant_id, quantity} lines plus a merge token -- never
 * prices or names (the server is the only price truth; the UI hydrates
 * display data through /products/?ids=...).
 *
 * The merge token identifies one guest-cart generation: POSTing the
 * same token twice to /cart/merge/ is a server-side no-op, so a lost
 * response or a double click can never double the lines. The token is
 * rotated whenever the guest cart is cleared after a SUCCESSFUL merge.
 */
const LINES_KEY = "cusin.guest_cart.v1.lines";
const TOKEN_KEY = "cusin.guest_cart.v1.token";

function validLine(line) {
  return (
    line &&
    Number.isInteger(line.product_id) &&
    line.product_id > 0 &&
    (line.variant_id === null || Number.isInteger(line.variant_id)) &&
    Number.isInteger(line.quantity) &&
    line.quantity >= 1
  );
}

export function loadGuestLines() {
  try {
    const parsed = JSON.parse(window.localStorage.getItem(LINES_KEY) || "[]");
    return Array.isArray(parsed) ? parsed.filter(validLine) : [];
  } catch {
    return [];
  }
}

export function saveGuestLines(lines) {
  try {
    window.localStorage.setItem(LINES_KEY, JSON.stringify(lines.filter(validLine)));
  } catch {
    // Private mode / full storage: the guest cart degrades to in-memory.
  }
}

export function clearGuestLines() {
  try {
    window.localStorage.removeItem(LINES_KEY);
    window.localStorage.removeItem(TOKEN_KEY);
  } catch {
    // ignore
  }
}

export function getMergeToken() {
  try {
    let token = window.localStorage.getItem(TOKEN_KEY);
    if (!token) {
      token = rotateMergeToken();
    }
    return token;
  } catch {
    return "session";
  }
}

export function rotateMergeToken() {
  const token =
    typeof crypto !== "undefined" && crypto.randomUUID
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  try {
    window.localStorage.setItem(TOKEN_KEY, token);
  } catch {
    // ignore
  }
  return token;
}

export function guestLineCount(lines) {
  return lines.reduce((sum, line) => sum + line.quantity, 0);
}
