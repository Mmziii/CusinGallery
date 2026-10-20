import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import SearchCombobox from "./SearchCombobox";
import AddressForm from "./AddressForm";
import apiClient from "../services/apiClient";

const PROVINCE_OPTIONS = [
  { value: "تهران", label: "تهران" },
  { value: "کرمان", label: "کرمان" },
  { value: "فارس", label: "فارس" },
  { value: "قزوین", label: "قزوین" },
];

const originalAdapter = apiClient.defaults.adapter;

beforeAll(() => {
  apiClient.defaults.adapter = async (config) => {
    const url = config.url || "";
    if (url === "/accounts/locations/") {
      return {
        data: {
          provinces: [
            { name: "تهران", cities: ["تهران", "شهریار"] },
            { name: "اصفهان", cities: ["اصفهان", "کاشان"] },
          ],
        },
        status: 200,
        statusText: "OK",
        headers: {},
        config,
      };
    }
    return originalAdapter(config);
  };
});

afterAll(() => {
  apiClient.defaults.adapter = originalAdapter;
});

afterEach(() => {
  cleanup();
  document.body.className = "";
  document.documentElement.className = "";
});

describe("SearchCombobox (Task 1)", () => {
  it("filters options and supports arrows, Enter and Escape", () => {
    const onChange = vi.fn();
    render(
      <SearchCombobox
        label="استان"
        value=""
        options={PROVINCE_OPTIONS}
        onChange={onChange}
      />
    );
    const input = screen.getByRole("combobox");
    fireEvent.change(input, { target: { value: "فار" } });
    expect(screen.getAllByRole("option")).toHaveLength(1);
    fireEvent.keyDown(input, { key: "Enter" });
    expect(onChange).toHaveBeenCalledWith("فارس");
    expect(input.getAttribute("aria-expanded")).toBe("false");

    fireEvent.keyDown(input, { key: "ArrowDown" });
    fireEvent.keyDown(input, { key: "Escape" });
    expect(input.getAttribute("aria-expanded")).toBe("false");
  });

  it("normalizes Persian and Arabic ی and ک when filtering", () => {
    const onChange = vi.fn();
    render(
      <SearchCombobox
        label="استان"
        value=""
        options={PROVINCE_OPTIONS}
        onChange={onChange}
      />
    );
    const input = screen.getByRole("combobox");

    // Arabic ك (U+0643) matches Persian ک (U+06A9)
    fireEvent.change(input, { target: { value: "كرمان" } });
    expect(screen.getAllByRole("option")).toHaveLength(1);
    expect(screen.getByRole("option").textContent).toBe("کرمان");

    // Arabic ي (U+064A) matches Persian ی (U+06CC)
    fireEvent.change(input, { target: { value: "قزوين" } });
    expect(screen.getAllByRole("option")).toHaveLength(1);
    expect(screen.getByRole("option").textContent).toBe("قزوین");
  });

  it("opens as a bottom sheet with title and locks body scroll on mobile (<768px)", () => {
    const originalMatchMedia = window.matchMedia;
    window.matchMedia = (query) => ({
      matches: query === "(max-width: 767px)",
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    });

    try {
      const onChange = vi.fn();
      render(
        <SearchCombobox
          label="استان"
          value=""
          options={PROVINCE_OPTIONS}
          onChange={onChange}
        />
      );

      const input = screen.getByRole("combobox");
      fireEvent.click(input);

      // Sheet with title «انتخاب استان»
      expect(screen.getByText("انتخاب استان")).toBeTruthy();
      expect(document.body.classList.contains("body--scroll-locked")).toBe(true);

      // Search box is present
      const searchBox = screen.getByPlaceholderText("جستجوی استان…");
      expect(searchBox).toBeTruthy();

      // Typing in mobile search box filters options
      fireEvent.change(searchBox, { target: { value: "تهران" } });
      const options = screen.getAllByRole("option");
      expect(options).toHaveLength(1);

      // Clicking option chooses it and closes sheet
      fireEvent.click(options[0]);
      expect(onChange).toHaveBeenCalledWith("تهران");
      expect(document.body.classList.contains("body--scroll-locked")).toBe(false);
    } finally {
      window.matchMedia = originalMatchMedia;
    }
  });

  it("clears and enables city when a new province is chosen in AddressForm", async () => {
    let address = { province: "تهران", city: "تهران" };
    const onChange = vi.fn((next) => {
      address = next;
    });

    const { rerender } = render(
      <AddressForm
        value={address}
        onChange={onChange}
      />
    );

    await waitFor(() => {
      expect(screen.getAllByRole("combobox").length).toBe(2);
    });

    const [provinceInput] = screen.getAllByRole("combobox");
    expect(provinceInput.value).toBe("تهران");

    // Click province combobox and choose Isfahan
    fireEvent.click(provinceInput);
    const options = screen.getAllByRole("option");
    const isfahanOption = options.find((opt) => opt.textContent === "اصفهان");
    expect(isfahanOption).toBeTruthy();
    fireEvent.click(isfahanOption);

    // onChange must have been called with city cleared
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ province: "اصفهان", city: "" })
    );

    // Re-render with new value
    rerender(
      <AddressForm
        value={{ province: "اصفهان", city: "" }}
        onChange={onChange}
      />
    );

    const [, cityInput] = screen.getAllByRole("combobox");
    expect(cityInput.disabled).toBe(false);
    expect(cityInput.value).toBe("");
  });
});
