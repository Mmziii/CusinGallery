/**
 * Task: address cards must show the phone in Persian digits like the rest
 * of the storefront («۰۹۱۲۱۱۱۲۲۳۳»), not the Latin source value. Display
 * only -- the API payload and the edit form keep Latin digits.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import apiClient from "../../services/apiClient";
import AddressesPage from "./AddressesPage";

const originalAdapter = apiClient.defaults.adapter;

const ADDRESSES = {
  count: 2,
  next: null,
  previous: null,
  results: [
    {
      id: 1,
      recipient_name: "سارا احمدی",
      phone: "09121112233",
      province: "تهران",
      city: "تهران",
      address: "خیابان ولیعصر، پلاک ۵",
      postal_code: "1234567890",
      unit: "3",
      building_number: "5",
      is_default: true,
    },
    {
      id: 2,
      recipient_name: "رضا کریمی",
      phone: "09354445566",
      province: "تهران",
      city: "تهران",
      address: "خیابان انقلاب",
      postal_code: "9876543210",
      unit: "1",
      building_number: "8",
      is_default: false,
    },
  ],
};

beforeEach(() => {
  apiClient.defaults.adapter = async (config) => {
    const url = config.url || "";
    if (url === "/accounts/locations/") {
      return { data: { provinces: [] }, status: 200, statusText: "OK", headers: {}, config };
    }
    if (url === "/accounts/addresses/") {
      return { data: ADDRESSES, status: 200, statusText: "OK", headers: {}, config };
    }
    return { data: {}, status: 200, statusText: "OK", headers: {}, config };
  };
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  apiClient.defaults.adapter = originalAdapter;
});

describe("address card phone digits", () => {
  it("renders every saved phone in Persian digits", async () => {
    render(<AddressesPage />);
    await screen.findByText("سارا احمدی");

    expect(screen.getByText("۰۹۱۲۱۱۱۲۲۳۳")).toBeTruthy();
    expect(screen.getByText("۰۹۳۵۴۴۴۵۵۶۶")).toBeTruthy();
    expect(screen.queryByText("09121112233")).toBeNull();
    expect(screen.queryByText("09354445566")).toBeNull();
  });
});
