/**
 * Part S5 item 6: the plot number (پلاک) and the unit (واحد) are required.
 *
 * The address form marks them with the same red star as every other
 * required field, tells the customer what to do when they have no unit,
 * normalizes Persian digits as they type, and shows the errors inline
 * without a round-trip. Addresses saved before this rule stay usable (the
 * checkout page only nudges, never blocks -- see CheckoutPage).
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AddressForm from "./AddressForm";
import { validateAddressPayload, validatePlotUnit } from "../utils/iranianFields";
import * as authApi from "../services/authApi";
import { fetchLocations } from "../services/siteApi";

vi.mock("../services/siteApi", () => ({
  fetchLocations: vi.fn().mockResolvedValue({ provinces: [] }),
}));
vi.mock("../services/authApi", () => ({
  createAddress: vi.fn().mockResolvedValue({ id: 1 }),
  updateAddress: vi.fn().mockResolvedValue({ id: 1 }),
}));
vi.mock("../utils/toast", () => ({ toast: vi.fn() }));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

const validAddress = {
  recipient_name: "سارا",
  phone: "09123456789",
  province: "تهران",
  city: "تهران",
  address: "خیابان ولیعصر",
  postal_code: "1234567890",
  building_number: "12",
  unit: "3",
};

describe("plot/unit client rules (Part S5 item 6)", () => {
  it("requires both fields and names them in Persian", () => {
    const errors = validateAddressPayload({ ...validAddress, building_number: "", unit: "" });
    expect(errors.building_number).toContain("پلاک");
    expect(errors.unit).toContain("واحد");
    // The helper the owner asked for, right in the message.
    expect(errors.unit).toContain("عدد ۰ را وارد کنید");
  });

  it("accepts «۰» as the documented value for a customer with no unit", () => {
    expect(validatePlotUnit("۰", { label: "واحد", noUnitHint: true })).toBe("");
    expect(validateAddressPayload({ ...validAddress, unit: "۰" })).toEqual({});
  });

  it("rejects non-numeric and too-long values", () => {
    expect(validatePlotUnit("الف", { label: "واحد" })).toContain("فقط عدد");
    expect(validatePlotUnit("1".repeat(21), { label: "واحد" })).toContain("۲۰");
  });

  it("does not require them when the caller opts out", () => {
    const errors = validateAddressPayload(
      { ...validAddress, building_number: "", unit: "" },
      { requirePlotAndUnit: false }
    );
    expect(errors).toEqual({});
  });
});

describe("AddressForm plot/unit fields (Part S5 item 6)", () => {
  it("shows both labels without «(اختیاری)» and marks them required", async () => {
    render(<AddressForm value={validAddress} onChange={() => {}} />);
    await waitFor(() => expect(fetchLocations).toHaveBeenCalled());

    const plot = screen.getByText("پلاک").closest("label");
    const unit = screen.getByText("واحد").closest("label");
    expect(plot.querySelector(".field__required")).not.toBeNull();
    expect(unit.querySelector(".field__required")).not.toBeNull();
    expect(plot.textContent).not.toContain("اختیاری");
    expect(unit.textContent).not.toContain("اختیاری");
    // The «if you have no unit, enter 0» helper.
    expect(unit.textContent).toContain("اگر واحد ندارید عدد ۰ را وارد کنید");
  });

  it("normalizes Persian digits to ASCII while typing", async () => {
    const onChange = vi.fn();
    render(<AddressForm value={{ ...validAddress, unit: "" }} onChange={onChange} />);

    fireEvent.change(screen.getByLabelText(/واحد/), { target: { value: "۱۲" } });

    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ unit: "12" }));
  });

  it("blocks saving an address without plot/unit and shows both errors inline", async () => {
    render(<AddressForm initial={{ ...validAddress, building_number: "", unit: "" }} onSaved={() => {}} />);
    await waitFor(() => expect(fetchLocations).toHaveBeenCalled());

    fireEvent.submit(screen.getByRole("button", { name: "افزودن آدرس" }).closest("form"));

    const alerts = await screen.findAllByRole("alert");
    const text = alerts.map((a) => a.textContent).join(" | ");
    expect(text).toContain("پلاک");
    expect(text).toContain("واحد");
    expect(authApi.createAddress).not.toHaveBeenCalled();
  });
});
