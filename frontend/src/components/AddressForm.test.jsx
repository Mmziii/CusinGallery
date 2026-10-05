/**
 * AddressForm tests (Part R3): province select drives a dependent city
 * select; "شهر دیگر" switches to free text; changing province resets a
 * city that no longer belongs; editing a legacy city shows it in the
 * free-text input.
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { afterEach, beforeAll, afterAll, describe, expect, it } from "vitest";

import apiClient from "../services/apiClient";
import AddressForm from "./AddressForm";

const LOCATIONS = {
  provinces: [
    { name: "فارس", cities: ["شیراز", "مرودشت"] },
    { name: "تهران", cities: ["تهران", "شهریار"] },
  ],
};

let originalAdapter;
beforeAll(() => {
  originalAdapter = apiClient.defaults.adapter;
  apiClient.defaults.adapter = async (config) => {
    if (config.url.includes("/accounts/locations/")) {
      return { data: LOCATIONS, status: 200, statusText: "OK", headers: {}, config };
    }
    return { data: {}, status: 200, statusText: "OK", headers: {}, config };
  };
});
afterAll(() => {
  apiClient.defaults.adapter = originalAdapter;
});
afterEach(cleanup);

// Controlled mode: a stateful wrapper so onChange updates actually flow
// back into the rendered props (the form derives its selects from them).
function controlled(initial = {}) {
  const holder = { value: initial };
  function Wrapper() {
    const [value, setValue] = useState(initial);
    holder.value = value;
    return <AddressForm value={value} onChange={setValue} compact />;
  }
  const utils = render(<Wrapper />);
  return { holder, ...utils };
}

describe("AddressForm location selects", () => {
  it("province select lists all provinces and city select depends on it", async () => {
    const { holder } = controlled();
    await waitFor(() => expect(screen.getByText("فارس")).toBeTruthy());

    const provinceSelect = screen.getByDisplayValue("انتخاب استان…");
    fireEvent.change(provinceSelect, { target: { value: "فارس" } });
    expect(holder.value.province).toBe("فارس");

    const citySelect = screen.getByDisplayValue("انتخاب شهر…");
    expect(screen.getByText("شیراز")).toBeTruthy();
    expect(screen.getByText("مرودشت")).toBeTruthy();

    fireEvent.change(citySelect, { target: { value: "شیراز" } });
    expect(holder.value.city).toBe("شیراز");
  });

  it("switching province resets a city that no longer belongs", async () => {
    const { holder } = controlled({ province: "فارس", city: "شیراز" });
    await waitFor(() => expect(screen.getByDisplayValue("شیراز")).toBeTruthy());

    fireEvent.change(screen.getByDisplayValue("فارس"), { target: { value: "تهران" } });
    expect(holder.value.province).toBe("تهران");
    expect(holder.value.city).toBe("");
    expect(screen.queryByDisplayValue("شیراز")).toBeNull();
  });

  it("choosing 'شهر دیگر' reveals a free-text city input", async () => {
    const { holder } = controlled({ province: "فارس", city: "" });
    await waitFor(() => expect(screen.getByDisplayValue("فارس")).toBeTruthy());

    fireEvent.change(screen.getByDisplayValue("انتخاب شهر…"), {
      target: { value: "__other__" },
    });
    const text = screen.getByPlaceholderText("نام شهر خود را بنویسید");
    fireEvent.change(text, { target: { value: "روستای من" } });
    expect(holder.value.city).toBe("روستای من");
  });

  it("an existing unknown city edits in the free-text input", async () => {
    controlled({ province: "فارس", city: "روستای قدیمی" });
    await waitFor(() => expect(screen.getByDisplayValue("فارس")).toBeTruthy());
    expect(screen.getByDisplayValue("روستای قدیمی")).toBeTruthy();
    expect(screen.getByDisplayValue("شهر دیگر…")).toBeTruthy();
  });
});
