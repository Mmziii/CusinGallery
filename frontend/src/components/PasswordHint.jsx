import PropTypes from "prop-types";

/**
 * Customer password guidance (Part 1). The storefront policy is only:
 * min 8 characters + ASCII-only. The static help line sits under every
 * customer password field (register, reset, change); the red warning
 * appears LIVE the moment Persian/Arabic characters are typed, because
 * that mistake is invisible otherwise (the field looks fine but the
 * server rejects it).
 *
 * Login deliberately shows none of this: login never applies password
 * policy, so existing passwords are never lectured or locked out.
 */
// Arabic block + Arabic Supplement (Persian letters and Arabic-Indic
// / extended Arabic digits all fall inside these two ranges).
const NON_ASCII_RE = /[\u0600-\u06FF\u0750-\u077F]/;

export function passwordHasNonAscii(value) {
  return NON_ASCII_RE.test(value || "");
}

function PasswordHint({ value }) {
  return (
    <>
      <p className="field-help">
        رمز عبور باید حداقل ۸ کاراکتر باشد. اگر از حروف استفاده می‌کنید، کیبورد را روی
        انگلیسی بگذارید.
      </p>
      {passwordHasNonAscii(value) ? (
        <p className="field-help field-help--error" role="alert">
          حروف فارسی/عربی در رمز عبور پذیرفته نمی‌شود؛ کیبورد را روی انگلیسی بگذارید.
        </p>
      ) : null}
    </>
  );
}

PasswordHint.propTypes = {
  value: PropTypes.string,
};

export default PasswordHint;
