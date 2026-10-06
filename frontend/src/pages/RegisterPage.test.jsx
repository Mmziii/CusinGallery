/**
 * Part S2 item 5: register form hygiene -- Persian/Arabic digit
 * normalization in the phone field AS THE USER TYPES, clear inline
 * Persian validation messages, whitespace trimming before submit, and
 * proper autocomplete attributes.
 */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { afterEach, beforeAll, afterAll, describe, expect, it } from "vitest";

import apiClient from "../services/apiClient";
import useAuthStore from "../store/useAuthStore";
import RegisterPage from "./RegisterPage";

const originalAdapter = apiClient.defaults.adapter;
let registerCalls = [];

beforeAll(() => {
  apiClient.defaults.adapter = async (config) => {
    const url = config.url || "";
    if (url === "/accounts/register/" && config.method === "post") {
      registerCalls.push(JSON.parse(config.data));
      return {
        data: { id: 1, phone: "09121112233", first_name: "", last_name: "" },
        status: 201,
        statusText: "Created",
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
  registerCalls = [];
  useAuthStore.setState({ user: null, isAuthenticated: false, isLoading: false, error: null });
});

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/register/"]}>
      <Routes>
        <Route path="/register/" element={<RegisterPage />} />
        <Route path="*" element={<div>home</div>} />
      </Routes>
    </MemoryRouter>
  );
}

describe("RegisterPage form hygiene (S2.5)", () => {
  it("normalizes Persian digits in the phone field as the user types", () => {
    renderPage();
    const phone = screen.getByLabelText(/شماره موبایل/);
    fireEvent.change(phone, { target: { value: "۰۹۱۲ ۱۱۱۲۲۳۳" } });
    // Digits converted to ASCII; spaces dropped by normalizePhone.
    expect(phone.value).toBe("09121112233");
  });

  it("shows an inline Persian error and makes NO API call for an invalid phone", () => {
    renderPage();
    fireEvent.change(screen.getByLabelText(/شماره موبایل/), { target: { value: "0912" } });
    fireEvent.change(screen.getByLabelText(/^رمز عبور/), { target: { value: "a-strong-passw0rd!" } });
    fireEvent.change(screen.getByLabelText(/^تکرار رمز عبور/), { target: { value: "a-strong-passw0rd!" } });
    fireEvent.click(screen.getByRole("button", { name: "ثبت‌نام" }));

    expect(screen.getByText(/شماره موبایل معتبر نیست/)).toBeTruthy();
    expect(registerCalls.length).toBe(0);
  });

  it("trims whitespace and posts the cleaned payload on valid submit", async () => {
    renderPage();
    fireEvent.change(screen.getByLabelText(/شماره موبایل/), { target: { value: "۰۹۱۲۱۱۱۲۲۳۳" } });
    fireEvent.change(screen.getByLabelText(/^نام$/), { target: { value: "  سارا  " } });
    fireEvent.change(screen.getByLabelText(/^رمز عبور/), { target: { value: "a-strong-passw0rd!" } });
    fireEvent.change(screen.getByLabelText(/^تکرار رمز عبور/), { target: { value: "a-strong-passw0rd!" } });
    fireEvent.click(screen.getByRole("button", { name: "ثبت‌نام" }));

    await screen.findByText("home");
    expect(registerCalls.length).toBe(1);
    expect(registerCalls[0].phone).toBe("09121112233");
    expect(registerCalls[0].first_name).toBe("سارا");
  });

  it("carries the right autocomplete hints for password managers", () => {
    renderPage();
    expect(screen.getByLabelText(/شماره موبایل/).getAttribute("autocomplete")).toBe("tel");
    expect(screen.getByLabelText(/^رمز عبور/).getAttribute("autocomplete")).toBe("new-password");
    expect(screen.getByLabelText(/^تکرار رمز عبور/).getAttribute("autocomplete")).toBe("new-password");
    expect(screen.getByLabelText(/ایمیل/).getAttribute("autocomplete")).toBe("email");
  });
});
