import PropTypes from "prop-types";
import { useEffect, useId, useRef, useState } from "react";
import Portal from "./Portal";

/** Editable ARIA combobox; a viewport-level bottom sheet on narrow screens. */
export default function SearchCombobox({ id, label, value, options, onChange, disabled, placeholder, invalid }) {
  const listId = useId();
  const input = useRef(null);
  const panel = useRef(null);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const [position, setPosition] = useState({});
  const selected = options.find(option => option.value === value)?.label || "";
  const filtered = options.filter(option => option.label.includes(query.trim()));
  const choose = option => { if (!option) return; onChange(option.value); setOpen(false); setQuery(""); input.current?.focus(); };
  const show = () => {
    if (disabled) return;
    const rect = input.current.getBoundingClientRect();
    setPosition({ top: rect.bottom + 6, left: rect.left, width: rect.width });
    setQuery(""); setActive(0); setOpen(true);
  };
  useEffect(() => {
    if (!open) return;
    const outside = event => { if (!input.current?.contains(event.target) && !panel.current?.contains(event.target)) setOpen(false); };
    const escape = event => { if (event.key === "Escape") { setOpen(false); input.current?.focus(); } };
    document.addEventListener("pointerdown", outside);
    document.addEventListener("keydown", escape);
    return () => { document.removeEventListener("pointerdown", outside); document.removeEventListener("keydown", escape); };
  }, [open]);
  const keyDown = event => {
    if (["ArrowDown", "ArrowUp"].includes(event.key)) {
      event.preventDefault();
      if (!open) show();
      else setActive(index => Math.max(0, Math.min(filtered.length - 1, index + (event.key === "ArrowDown" ? 1 : -1))));
    } else if (event.key === "Enter" && open) { event.preventDefault(); choose(filtered[active]); }
    else if (event.key === "Tab") setOpen(false);
  };
  return <span className="search-combobox">
    <input id={id} ref={input} role="combobox" aria-label={label} aria-expanded={open} aria-controls={listId}
      aria-autocomplete="list" aria-activedescendant={open && filtered[active] ? `${listId}-${active}` : undefined}
      aria-invalid={invalid} disabled={disabled} placeholder={placeholder} autoComplete="off"
      value={open ? query : selected} onClick={show} onKeyDown={keyDown}
      onChange={event => {
        const text = event.target.value; if (!open) show(); setQuery(text); setActive(0);
        const exact = options.find(option => option.label === text); if (exact) onChange(exact.value);
      }} />
    {open ? <Portal><span ref={panel} className="combobox-panel" style={position}>
      <span className="combobox-panel__head">{label}<button type="button" aria-label="بستن فهرست" onClick={() => { setOpen(false); input.current?.focus(); }}>×</button></span>
      <input className="combobox-panel__search" aria-label={`جستجوی ${label}`} placeholder={`جستجوی ${label}…`} value={query} onChange={event => { setQuery(event.target.value); setActive(0); }} onKeyDown={keyDown} />
      <span role="listbox" id={listId} aria-label={label} className="combobox-panel__options">
        {filtered.map((option, index) => <span role="option" id={`${listId}-${index}`} key={option.value} aria-selected={option.value === value}
          className={index === active ? "is-active" : ""} onMouseDown={event => event.preventDefault()} onClick={event => { event.preventDefault(); choose(option); }}>{option.label}</span>)}
        {!filtered.length ? <span className="muted">نتیجه‌ای پیدا نشد.</span> : null}
      </span>
    </span></Portal> : null}
  </span>;
}
SearchCombobox.propTypes = {
  id: PropTypes.string, label: PropTypes.string.isRequired, value: PropTypes.string,
  options: PropTypes.arrayOf(PropTypes.shape({ value: PropTypes.string, label: PropTypes.string })).isRequired,
  onChange: PropTypes.func.isRequired, disabled: PropTypes.bool, placeholder: PropTypes.string, invalid: PropTypes.bool,
};
