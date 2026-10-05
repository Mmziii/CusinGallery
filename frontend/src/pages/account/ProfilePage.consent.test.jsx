/**
 * Part R5 item 11: the marketing-SMS consent toggle on the account page.
 * Verifies it renders UNCHECKED for a profile whose consent is off (the
 * server default), and that ticking it + saving PATCHes
 * marketing_sms_consent=true to /accounts/me/.
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it } from "vitest";

import apiClient from "../../services/apiClient";
import useAuthStore from "../../store/useAuthStore";
import ProfilePage from "./ProfilePage";

const USER = {
  id: 1,
  first_name: "تست",
  last_name: "کاربر",
  email: "test@example.com",
  phone: "+989120000001",
  is_staff: false,
  date_joined: "2026-01-01T00:00:00Z",
  last_login: null,
  marketing_sms_consent: false,
};

let patchBodies = [];
const originalAdapter = apiClient.defaults.adapter;

beforeAll(() => {
  apiClient.defaults.adapter = async (config) => {
    const url = config.url || "";
    const method = (config.method || "get").toLowerCase();
    if (url === "/accounts/me/" && method === "patch") {
      patchBodies.push(JSON.parse(config.data || "{}"));
      return {
        data: { ...USER, ...JSON.parse(config.data || "{}") },
        status: 200, statusText: "OK", headers: {}, config,
      };
    }
    return originalAdapter(config);
  };
});
afterAll(() => {
  apiClient.defaults.adapter = originalAdapter;
});
beforeEach(() => {
  patchBodies = [];
  useAuthStore.setState({ user: USER, isAuthenticated: true, isLoading: false, error: null });
});
afterEach(() => cleanup());

function renderProfile() {
  return render(
    <MemoryRouter>
      <ProfilePage />
    </MemoryRouter>
  );
}

describe("profile page marketing consent", () => {
  it("is rendered unchecked when the profile has not opted in", () => {
    renderProfile();
    const checkbox = screen.getByRole("checkbox");
    expect(checkbox.checked).toBe(false);
    // The consent text makes the opt-in nature explicit.
    expect(screen.getByText(/پیامک یادآور سبد خرید/)).toBeTruthy();
    expect(screen.getByText(/خاموش است/)).toBeTruthy();
  });

  it("renders checked when the profile already opted in", () => {
    useAuthStore.setState({ user: { ...USER, marketing_sms_consent: true } });
    renderProfile();
    expect(screen.getByRole("checkbox").checked).toBe(true);
  });

  it("saves the opt-in via PATCH /accounts/me/", async () => {
    renderProfile();
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(screen.getByText("ذخیره تغییرات"));

    await waitFor(() => expect(patchBodies.length).toBe(1));
    expect(patchBodies[0]).toMatchObject({ marketing_sms_consent: true });
    await waitFor(() => expect(screen.getByText("ذخیره شد.")).toBeTruthy());
  });
});
