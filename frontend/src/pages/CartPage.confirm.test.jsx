/*
 * PR 20: the cart's destructive actions go through the styled confirm
 * dialog (hooks/useConfirm), never through window.confirm() -- the
 * native prompt announced itself as "193.5.44.126 says" on iPhone.
 * These drive the REAL page + store against a scripted cart API.
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import apiClient from "../services/apiClient";
import useAuthStore from "../store/useAuthStore";
import useCartStore from "../store/useCartStore";
import CartPage from "./CartPage";

const originalAdapter = apiClient.defaults.adapter;
const realFetchCart = useCartStore.getState().fetchCart;

const line = (id, name, quantity = 1) => ({
  id,
  quantity,
  available_stock: 5,
  is_available: true,
  product: { id: 100 + id, name, slug: `p-${id}` },
  price_info: { price: 1000, compare_at_price: null, is_on_sale: false, discount_amount: 0, discount_percentage: 0 },
  line_total: 1000 * quantity,
});

let serverItems;
let deleteCalls;
let patchCalls;

const asCart = (items) => ({
  items,
  item_count: items.reduce((n, item) => n + item.quantity, 0),
  subtotal: items.reduce((n, item) => n + item.line_total, 0),
});

beforeEach(() => {
  serverItems = [line(1, "کالای اول"), line(2, "کالای دوم", 2)];
  deleteCalls = [];
  patchCalls = [];
  vi.spyOn(window, "confirm");

  apiClient.defaults.adapter = async (config) => {
    const url = config.url || "";
    const method = (config.method || "get").toLowerCase();
    const detail = url.match(/^\/cart\/items\/(\d+)\/$/);
    if (detail && method === "delete") {
      deleteCalls.push(Number(detail[1]));
      serverItems = serverItems.filter((item) => item.id !== Number(detail[1]));
      return { data: asCart(serverItems), status: 200, statusText: "OK", headers: {}, config };
    }
    if (detail && method === "patch") {
      const body = JSON.parse(config.data || "{}");
      patchCalls.push({ id: Number(detail[1]), quantity: body.quantity });
      serverItems = serverItems
        .map((item) =>
          item.id === Number(detail[1])
            ? { ...item, quantity: body.quantity, line_total: body.quantity * 1000 }
            : item
        )
        .filter((item) => item.quantity > 0);
      return { data: asCart(serverItems), status: 200, statusText: "OK", headers: {}, config };
    }
    return originalAdapter(config);
  };

  useAuthStore.setState({ isAuthenticated: true, isLoading: false, user: { first_name: "سارا" } });
  useCartStore.setState({
    cart: asCart(serverItems),
    error: null,
    isLoading: false,
    fetchCart: vi.fn(),
  });
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  apiClient.defaults.adapter = originalAdapter;
  useCartStore.setState({ fetchCart: realFetchCart, cart: null });
});

function renderCart() {
  return render(
    <MemoryRouter>
      <CartPage />
    </MemoryRouter>
  );
}

describe("cart destructive actions use the styled dialog", () => {
  it("asks in the dialog before removing a line; «انصراف» keeps it, «حذف» deletes", async () => {
    const { container } = renderCart();
    await screen.findByText("کالای اول");

    const rowRemove = () =>
      [...container.querySelectorAll(".cart-item")].find((row) =>
        row.textContent.includes("کالای اول")
      ).querySelector(".link-danger");

    // Cancel: no request, the line stays.
    fireEvent.click(rowRemove());
    const dialog = await screen.findByRole("alertdialog");
    expect(within(dialog).getByText("این کالا از سبد خرید حذف شود؟")).toBeTruthy();
    fireEvent.click(within(dialog).getByRole("button", { name: "انصراف" }));
    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull());
    expect(deleteCalls).toEqual([]);
    expect(screen.getByText("کالای اول")).toBeTruthy();

    // Confirm: exactly one DELETE, the line is gone, the other stays.
    fireEvent.click(rowRemove());
    const dialogAgain = await screen.findByRole("alertdialog");
    fireEvent.click(within(dialogAgain).getByRole("button", { name: "حذف" }));
    await waitFor(() => expect(screen.queryByText("کالای اول")).toBeNull());
    expect(deleteCalls).toEqual([1]);
    expect(screen.getByText("کالای دوم")).toBeTruthy();

    expect(window.confirm).not.toHaveBeenCalled();
  });

  it("asks in the dialog before dropping the last unit to zero", async () => {
    const { container } = renderCart();
    await screen.findByText("کالای اول");

    const row = [...container.querySelectorAll(".cart-item")].find((node) =>
      node.textContent.includes("کالای اول")
    );
    fireEvent.click(within(row).getByRole("button", { name: "کاهش تعداد" }));
    const dialog = await screen.findByRole("alertdialog");
    expect(patchCalls).toEqual([]);

    fireEvent.click(within(dialog).getByRole("button", { name: "حذف" }));
    await waitFor(() => expect(screen.queryByText("کالای اول")).toBeNull());
    expect(patchCalls).toEqual([{ id: 1, quantity: 0 }]);
    expect(window.confirm).not.toHaveBeenCalled();
  });
});
