/**
 * Part S2 item 8: focus trap for drawers/dialogs. Verifies focus moves
 * into the surface, Tab cycles inside it (wrapping both ways), Escape
 * closes it, and focus returns to the opener when it closes.
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it } from "vitest";

import useFocusTrap from "./useFocusTrap";
import { useRef } from "react";

function Harness() {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  useFocusTrap(ref, open, () => setOpen(false));
  return (
    <div>
      <button type="button" onClick={() => setOpen(true)}>open trigger</button>
      {open ? (
        <div ref={ref} role="dialog" aria-label="dialog">
          <button type="button">first</button>
          <button type="button">second</button>
        </div>
      ) : null}
    </div>
  );
}

describe("useFocusTrap (S2.8)", () => {
  it("moves focus inside, traps Tab, closes on Escape, restores focus", () => {
    render(<Harness />);
    const trigger = screen.getByText("open trigger");
    trigger.focus();
    fireEvent.click(trigger);

    // Focus moved to the first focusable element inside the dialog.
    expect(document.activeElement).toBe(screen.getByText("first"));

    // Tab from the last element wraps to the first.
    screen.getByText("second").focus();
    fireEvent.keyDown(document, { key: "Tab" });
    expect(document.activeElement).toBe(screen.getByText("first"));

    // Shift+Tab from the first element wraps to the last.
    fireEvent.keyDown(document, { key: "Tab", shiftKey: true });
    expect(document.activeElement).toBe(screen.getByText("second"));

    // Escape closes and focus returns to the trigger.
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(trigger);
  });
});
