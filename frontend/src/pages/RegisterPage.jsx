import PasswordHint from "../components/PasswordHint.jsx";
import { usePageMeta } from "../hooks/usePageMeta";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { Alert, errorMessage } from "../components/ui";
import useAuthStore from "../store/useAuthStore";
import { isValidIranianPhone, normalizePhone } from "../utils/iranianFields";

function RegisterPage() {
  usePageMeta({ title: "ثبت‌نام", path: "/register/" });
  const navigate = useNavigate();
  const { register, isLoading } = useAuthStore();

  const [form, setForm] = useState({
    phone: "",
    email: "",
    first_name: "",
    last_name: "",
    password: "",
    password_confirm: "",
  });
  const [error, setError] = useState(null);
  // Part S2 item 5: instant inline feedback for the phone field, using the
  // same normalization/validation rules as the address form and backend.
  const [phoneError, setPhoneError] = useState(null);

  const setField = (key) => (event) => {
    // Part S2 item 5: normalize Persian/Arabic digits in the phone field
    // AS THE USER TYPES; text fields are trimmed on submit.
    const value = key === "phone" ? normalizePhone(event.target.value) : event.target.value;
    setForm((f) => ({ ...f, [key]: value }));
    if (key === "phone") {
      setPhoneError(
        value && !isValidIranianPhone(value)
          ? "شماره موبایل معتبر نیست (مانند 09123456789)."
          : null
      );
    }
  };

  const submit = async (event) => {
    event.preventDefault();
    setError(null);
    if (!form.phone) {
      setPhoneError("شماره موبایل را وارد کنید.");
      return;
    }
    if (!isValidIranianPhone(form.phone)) {
      setPhoneError("شماره موبایل معتبر نیست (مانند 09123456789).");
      return;
    }
    // Part S2 item 5: trim stray whitespace from every text value.
    const payload = Object.fromEntries(
      Object.entries(form).map(([key, value]) => [key, typeof value === "string" ? value.trim() : value])
    );
    const result = await register(payload);
    if (result.success) {
      navigate("/", { replace: true });
    } else {
      setError(errorMessage(result.error));
    }
  };

  return (
    <div className="auth-page">
      <form className="auth-card" onSubmit={submit}>
        <h1>ثبت‌نام</h1>

        <label className={phoneError ? "field field--error" : "field"}>
          <span>
            شماره موبایل <span className="field__required" aria-hidden="true">*</span>
          </span>
          <input
            type="tel"
            dir="ltr"
            inputMode="tel"
            autoComplete="tel"
            value={form.phone}
            onChange={setField("phone")}
            aria-invalid={Boolean(phoneError)}
            className={phoneError ? "is-invalid" : undefined}
            required
          />
          <span className="muted field__hint">مثال: 09123456789 — اعداد فارسی هم پذیرفته می‌شود.</span>
          {phoneError ? <span className="field__error" role="alert">{phoneError}</span> : null}
        </label>
        <label className="field">
          <span>ایمیل (اختیاری)</span>
          <input type="email" dir="ltr" autoComplete="email" value={form.email} onChange={setField("email")} />
        </label>
        <div className="field-row">
          <label className="field">
            <span>نام</span>
            <input type="text" autoComplete="given-name" value={form.first_name} onChange={setField("first_name")} />
          </label>
          <label className="field">
            <span>نام خانوادگی</span>
            <input type="text" autoComplete="family-name" value={form.last_name} onChange={setField("last_name")} />
          </label>
        </div>
        <label className="field">
          <span>
            رمز عبور <span className="field__required" aria-hidden="true">*</span>
          </span>
          <input type="password" autoComplete="new-password" value={form.password} onChange={setField("password")} required />
          <PasswordHint value={form.password} />
        </label>
        <label className="field">
          <span>
            تکرار رمز عبور <span className="field__required" aria-hidden="true">*</span>
          </span>
          <input type="password" autoComplete="new-password" value={form.password_confirm} onChange={setField("password_confirm")} required />
        </label>

        {error ? <Alert>{error}</Alert> : null}

        <button type="submit" className="btn btn--primary btn--block" disabled={isLoading}>
          {isLoading ? "در حال ثبت‌نام…" : "ثبت‌نام"}
        </button>

        <div className="auth-card__links">
          <Link to="/login/">حساب دارید؟ ورود</Link>
        </div>
      </form>
    </div>
  );
}

export default RegisterPage;
