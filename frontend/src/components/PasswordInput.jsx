import PropTypes from "prop-types";
import { useId, useState } from "react";

import Icon from "./Icon";

/**
 * Password field with a show/hide eye button (Audit 19 item 3).
 *
 * ONE reusable component for every password field in the storefront
 * (login, register, password reset/confirm, change password in the
 * account) so the eye behaves identically everywhere:
 *
 *   * tap = `type="text"` (password visible), tap again = `type="password"`;
 *   * eye / eye-off icons, `aria-label` «نمایش رمز» which becomes «پنهان کردن رمز»,
 *     `aria-pressed` reflecting the state;
 *   * the button sits at the INLINE END of the field -- that is the LEFT
 *     side in this RTL layout, the side Persian shoppers expect;
 *   * 40px tap target, `type="button"` so it can never submit the form.
 *
 * Every other <input> prop (value, onChange, autoComplete, required,
 * disabled, dir, id/name, aria-*) is forwarded untouched, so the
 * component is a drop-in replacement for the plain input it replaced.
 */
function PasswordInput({ id, className = "", ...inputProps }) {
  const [visible, setVisible] = useState(false);
  const generatedId = useId();
  const inputId = id || `password-${generatedId.replace(/[^a-zA-Z0-9_-]/g, "")}`;
  const label = visible ? "پنهان کردن رمز" : "نمایش رمز";

  return (
    <span className={`password-field ${className}`.trim()}>
      <input
        {...inputProps}
        id={inputId}
        className="password-field__input"
        type={visible ? "text" : "password"}
      />
      <button
        type="button"
        className="password-field__toggle"
        aria-label={label}
        aria-pressed={visible}
        aria-controls={inputId}
        title={label}
        onClick={() => setVisible((value) => !value)}
      >
        <Icon name={visible ? "eye-off" : "eye"} size={18} />
      </button>
    </span>
  );
}

PasswordInput.propTypes = {
  /** id of the input; also referenced by the toggle's aria-controls. */
  id: PropTypes.string,
  className: PropTypes.string,
};

export default PasswordInput;
