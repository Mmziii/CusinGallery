/*
 * PR 20: the styled confirmation dialog that replaces window.confirm()
 * (which announced itself as "193.5.44.126 says" on iPhone).
 *
 * Contract: `confirm(...)` returns a Promise<boolean> that resolves
 * true ONLY from the danger button; «انصراف», Escape and a backdrop tap
 * all resolve false. The surface is a real modal alertdialog rendered
 * through the body Portal, focus-trapped (the safe button first) with
 * focus restored to the opener. And: no storefront page may call the
 * native confirm ever again (source guard at the bottom).
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import useConfirm from "./useConfirm";

const HERE = dirname(fileURLToPath(import.meta.url));

function Probe() {
  const { confirm, dialog } = useConfirm();
  const [result, setResult] = useState("pending");
  return (
    <>
      <button
        type="button"
        onClick={async () => setResult(String(await confirm("این کالا از سبد خرید حذف شود؟")))}
      >
        حذف از سبد
      </button>
      <output data-testid="result">{result}</output>
      {dialog}
    </>
  );
}

async function openDialog() {
  render(<Probe />);
  const opener = screen.getByRole("button", { name: "حذف از سبد" });
  opener.focus();
  fireEvent.click(opener);
  return screen.findByRole("alertdialog");
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("useConfirm / ConfirmDialog", () => {
  it("opens a styled alertdialog with the message and «حذف»/«انصراف», never window.confirm", async () => {
    const nativeConfirm = vi.spyOn(window, "confirm");
    const dialog = await openDialog();

    expect(dialog.getAttribute("aria-modal")).toBe("true");
    expect(within(dialog).getByText("این کالا از سبد خرید حذف شود؟")).toBeTruthy();
    expect(within(dialog).getByRole("button", { name: "حذف" }).className).toContain("btn--danger");
    expect(within(dialog).getByRole("button", { name: "انصراف" })).toBeTruthy();
    // Rendered through the portal: a direct child of <body>.
    expect(dialog.closest(".confirm-dialog").parentElement).toBe(document.body);
    expect(nativeConfirm).not.toHaveBeenCalled();
  });

  it("resolves true only from the danger button, then closes", async () => {
    const dialog = await openDialog();
    fireEvent.click(within(dialog).getByRole("button", { name: "حذف" }));
    await waitFor(() => expect(screen.getByTestId("result").textContent).toBe("true"));
    expect(screen.queryByRole("alertdialog")).toBeNull();
  });

  it("resolves false from «انصراف»", async () => {
    const dialog = await openDialog();
    fireEvent.click(within(dialog).getByRole("button", { name: "انصراف" }));
    await waitFor(() => expect(screen.getByTestId("result").textContent).toBe("false"));
    expect(screen.queryByRole("alertdialog")).toBeNull();
  });

  it("resolves false on Escape", async () => {
    const dialog = await openDialog();
    fireEvent.keyDown(document.activeElement, { key: "Escape" });
    await waitFor(() => expect(screen.getByTestId("result").textContent).toBe("false"));
    expect(screen.queryByRole("alertdialog")).toBeNull();
  });

  it("resolves false on a backdrop tap", async () => {
    await openDialog();
    fireEvent.click(document.querySelector(".confirm-dialog__backdrop"));
    await waitFor(() => expect(screen.getByTestId("result").textContent).toBe("false"));
    expect(screen.queryByRole("alertdialog")).toBeNull();
  });

  it("traps focus (safe button first) and restores it to the opener", async () => {
    const dialog = await openDialog();
    const cancel = within(dialog).getByRole("button", { name: "انصراف" });
    const danger = within(dialog).getByRole("button", { name: "حذف" });

    // A destructive button is never the default focus.
    await waitFor(() => expect(document.activeElement).toBe(cancel));

    // Tab cycles inside the dialog: last -> first, first -> last.
    danger.focus();
    fireEvent.keyDown(danger, { key: "Tab" });
    expect(document.activeElement).toBe(cancel);
    fireEvent.keyDown(cancel, { key: "Tab", shiftKey: true });
    expect(document.activeElement).toBe(danger);

    fireEvent.click(cancel);
    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull());
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "حذف از سبد" }));
  });
});

describe("no native confirm() survives in the storefront", () => {
  it("keeps window.confirm out of the former call sites", () => {
    for (const relative of [
      "../pages/CartPage.jsx",
      "../pages/WishlistPage.jsx",
      "../pages/account/AddressesPage.jsx",
    ]) {
      const source = readFileSync(join(HERE, relative), "utf8");
      expect(source, relative).not.toMatch(/window\.confirm\s*\(/);
      expect(source, relative).toContain("useConfirm");
    }
  });
});
