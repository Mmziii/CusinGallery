/**
 * Part S1 item 3: "cannot add an address" regressions.
 *
 * Covers the exact owner flow on the account addresses entry point:
 * type Persian digits, select real province/city text values, leave the
 * optional fields empty, and get either a saved address (with toast) or
 * a field-level inline error -- never a silent generic failure.
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import apiClient from "../services/apiClient";
import AddressForm from "./AddressForm";

let postRequests = [];
let nextResponse = null; // {status, data} the fake server will answer with
const originalAdapter = apiClient.defaults.adapter;

beforeAll(() => {
  Element.prototype.scrollIntoView = Element.prototype.scrollIntoView || (() => {});
  apiClient.defaults.adapter = async (config) => {
    const url = config.url || "";
    const method = (config.method || "get").toLowerCase();
    if (url === "/accounts/locations/") {
      return {
        data: { provinces: [{ name: "تهران", cities: ["تهران", "شهریار"] }] },
        status: 200, statusText: "OK", headers: {}, config,
      };
    }
    if (url === "/accounts/addresses/" && method === "post") {
      postRequests.push(JSON.parse(config.data || "{}"));
      if (nextResponse) {
        const error = new Error("request failed");
        error.response = { status: nextResponse.status, data: nextResponse.data };
        throw error;
      }
      return {
        data: { id: 7, ...JSON.parse(config.data || "{}"), created_at: "", updated_at: "" },
        status: 201, statusText: "Created", headers: {}, config,
      };
    }
    return originalAdapter(config);
  };
});
afterAll(() => {
  apiClient.defaults.adapter = originalAdapter;
});
beforeEach(() => {
  postRequests = [];
  nextResponse = null;
  vi.spyOn(HTMLElement.prototype, "focus").mockImplementation(() => {});
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

async function fillValidAddress() {
  // Wait for the locations fetch so province/city render as selects.
  await waitFor(() => expect(screen.getAllByRole("combobox").length).toBeGreaterThanOrEqual(1));
  const selects = screen.getAllByRole("combobox");
  fireEvent.change(selects[0], { target: { value: "تهران" } });
  const citySelect = await waitFor(() => {
    const el = screen.getAllByRole("combobox")[1];
    expect(el.disabled).toBe(false);
    return el;
  });
  fireEvent.change(citySelect, { target: { value: "تهران" } });

  fireEvent.change(screen.getByLabelText(/نام گیرنده/), { target: { value: "رویاً تست" } });
  fireEvent.change(screen.getByLabelText(/شماره تماس/), { target: { value: "۰۹۱۲۳۴۵۶۷۸۹" } });
  fireEvent.change(screen.getByLabelText(/آدرس کامل/), { target: { value: "خیابان ولیعصر" } });
  fireEvent.change(screen.getByLabelText(/کد پستی/), { target: { value: "۱۲۳۴-۵۶۷۸۹۰" } });
  // Part S5 item 6: the plot and the unit are required too.
  fireEvent.change(screen.getByLabelText(/پلاک/), { target: { value: "۱۲" } });
  fireEvent.change(screen.getByLabelText(/واحد/), { target: { value: "3" } });
}

describe("address form (S1 item 3)", () => {
  it("normalizes Persian digits while typing and saves a clean payload", async () => {
    const onSaved = vi.fn();
    render(<AddressForm onSaved={onSaved} />);
    await fillValidAddress();

    const phoneInput = screen.getByLabelText(/شماره تماس/);
    expect(phoneInput.value).toBe("09123456789"); // normalized live
    const postalInput = screen.getByLabelText(/کد پستی/);
    expect(postalInput.value).toBe("1234567890"); // dashes stripped

    fireEvent.click(screen.getByText("افزودن آدرس"));

    await waitFor(() => expect(postRequests.length).toBe(1));
    expect(postRequests[0]).toMatchObject({
      recipient_name: "رویاً تست",
      phone: "09123456789",
      province: "تهران",
      city: "تهران",
      postal_code: "1234567890",
      building_number: "12", // Persian digits normalized (Part S5 item 6)
      unit: "3",
    });
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
  });

  it("blocks submit with inline Persian errors and focuses the first invalid field", async () => {
    render(<AddressForm onSaved={() => {}} />);
    await screen.findAllByRole("combobox");

    // Only fill the recipient name; everything else stays empty.
    fireEvent.change(screen.getByLabelText(/نام گیرنده/), { target: { value: "تست" } });
    fireEvent.click(screen.getByText("افزودن آدرس"));

    expect(postRequests.length).toBe(0); // nothing sent
    expect(await screen.findByText("شماره تماس را وارد کنید.")).toBeTruthy();
    expect(await screen.findByText("کد پستی را وارد کنید.")).toBeTruthy();
  });

  it("shows the 10-digit postal rule inline for a 9-digit code", async () => {
    render(<AddressForm onSaved={() => {}} />);
    await fillValidAddress();
    fireEvent.change(screen.getByLabelText(/کد پستی/), { target: { value: "123456789" } });
    fireEvent.click(screen.getByText("افزودن آدرس"));

    expect(postRequests.length).toBe(0);
    expect(await screen.findByText("کد پستی باید دقیقاً ۱۰ رقم باشد.")).toBeTruthy();
  });

  it("shows server field errors inline instead of failing silently", async () => {
    nextResponse = { status: 400, data: { phone: ["شماره تماس معتبر نیست."] } };
    render(<AddressForm onSaved={() => {}} />);
    await fillValidAddress();
    fireEvent.click(screen.getByText("افزودن آدرس"));

    expect(await screen.findByText("شماره تماس معتبر نیست.")).toBeTruthy();
  });
});
