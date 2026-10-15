import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import SearchCombobox from "./SearchCombobox";
it("filters options and supports arrows, Enter and Escape", () => {
 const onChange = vi.fn();
 render(<SearchCombobox label="استان" value="" options={[{value:"تهران",label:"تهران"},{value:"فارس",label:"فارس"}]} onChange={onChange} />);
 const input = screen.getByRole("combobox");
 fireEvent.change(input,{target:{value:"فار"}});
 expect(screen.getAllByRole("option")).toHaveLength(1);
 fireEvent.keyDown(input,{key:"Enter"});
 expect(onChange).toHaveBeenCalledWith("فارس");
 expect(input.getAttribute("aria-expanded")).toBe("false");
 fireEvent.keyDown(input,{key:"ArrowDown"});
 fireEvent.keyDown(input,{key:"Escape"});
 expect(input.getAttribute("aria-expanded")).toBe("false");
});
