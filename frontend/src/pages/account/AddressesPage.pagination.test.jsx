/*
 * Saved-address mutations must re-read the complete DRF collection. This
 * exercises the actual authApi/pagination adapter instead of replacing it
 * with a service mock, so a paginated response can never become a render-time
 * `map` error or leave a stale default flag on screen.
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import apiClient from "../../services/apiClient";
import AddressesPage from "./AddressesPage";

const originalAdapter = apiClient.defaults.adapter;
const page = (results) => ({ count: results.length, next: null, previous: null, results });
const ok = (data, config, status = 200) => ({ data, status, statusText: "OK", headers: {}, config });

const address = (id, recipient_name, is_default = false) => ({
  id,
  recipient_name,
  phone: "09121112233",
  province: "تهران",
  city: "تهران",
  address: "خیابان ولیعصر، پلاک ۵",
  postal_code: "1234567890",
  unit: "3",
  building_number: "5",
  is_default,
});

function cardFor(name) {
  return screen.getByText(name).closest(".address-card");
}

describe("saved-address collection refreshes", () => {
  let addresses;
  let addressGets;

  beforeEach(() => {
    addresses = [address(1, "سارا احمدی", true), address(2, "رضا کریمی")];
    addressGets = 0;
    vi.spyOn(window, "confirm").mockReturnValue(true);

    apiClient.defaults.adapter = async (config) => {
      const url = config.url || "";
      const method = (config.method || "get").toLowerCase();
      if (url === "/accounts/locations/") return ok({ provinces: [] }, config);
      if (url === "/accounts/addresses/" && method === "get") {
        addressGets += 1;
        return ok(page(addresses), config);
      }
      if (url === "/accounts/addresses/" && method === "post") {
        const body = JSON.parse(config.data || "{}");
        const saved = { id: 3, ...body, is_default: false };
        addresses = [...addresses, saved];
        return ok(saved, config, 201);
      }
      const detail = url.match(/^\/accounts\/addresses\/(\d+)\/$/);
      if (detail && method === "patch") {
        const id = Number(detail[1]);
        const patch = JSON.parse(config.data || "{}");
        addresses = addresses.map((item) => (item.id === id ? { ...item, ...patch } : item));
        return ok(addresses.find((item) => item.id === id), config);
      }
      if (detail && method === "delete") {
        const id = Number(detail[1]);
        addresses = addresses.filter((item) => item.id !== id);
        return ok(null, config, 204);
      }
      const makeDefault = url.match(/^\/accounts\/addresses\/(\d+)\/set-default\/$/);
      if (makeDefault && method === "post") {
        const id = Number(makeDefault[1]);
        addresses = addresses.map((item) => ({ ...item, is_default: item.id === id }));
        return ok(addresses.find((item) => item.id === id), config);
      }
      throw new Error(`unexpected ${method} ${url}`);
    };
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    apiClient.defaults.adapter = originalAdapter;
  });

  it("re-fetches the paginated collection after default, edit and delete", async () => {
    render(<AddressesPage />);
    await screen.findByText("سارا احمدی");
    expect(addressGets).toBe(1);

    fireEvent.click(within(cardFor("رضا کریمی")).getByRole("button", { name: "پیش‌فرض" }));
    await waitFor(() => expect(addressGets).toBe(2));
    expect(within(cardFor("رضا کریمی")).getByText("پیش‌فرض")).toBeTruthy();

    fireEvent.click(within(cardFor("رضا کریمی")).getByRole("button", { name: "ویرایش" }));
    fireEvent.change(screen.getByLabelText(/^شهر/), { target: { value: "کرج" } });
    fireEvent.click(screen.getByRole("button", { name: "ذخیره تغییرات" }));
    await waitFor(() => expect(addressGets).toBe(3));
    expect(within(cardFor("رضا کریمی")).getByText(/کرج/)).toBeTruthy();

    fireEvent.click(within(cardFor("رضا کریمی")).getByRole("button", { name: "حذف" }));
    await waitFor(() => expect(addressGets).toBe(4));
    expect(screen.queryByText("رضا کریمی")).toBeNull();
  });
});
