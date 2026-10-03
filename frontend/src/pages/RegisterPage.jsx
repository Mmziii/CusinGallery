import { usePageMeta } from "../hooks/usePageMeta";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { Alert, errorMessage } from "../components/ui";
import useAuthStore from "../store/useAuthStore";

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

  const setField = (key) => (event) => setForm((f) => ({ ...f, [key]: event.target.value }));

  const submit = async (event) => {
    event.preventDefault();
    setError(null);
    const result = await register(form);
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

        <label className="field">
          <span>شماره موبایل *</span>
          <input type="tel" dir="ltr" value={form.phone} onChange={setField("phone")} required />
        </label>
        <label className="field">
          <span>ایمیل (اختیاری)</span>
          <input type="email" dir="ltr" value={form.email} onChange={setField("email")} />
        </label>
        <div className="field-row">
          <label className="field">
            <span>نام</span>
            <input type="text" value={form.first_name} onChange={setField("first_name")} />
          </label>
          <label className="field">
            <span>نام خانوادگی</span>
            <input type="text" value={form.last_name} onChange={setField("last_name")} />
          </label>
        </div>
        <label className="field">
          <span>رمز عبور *</span>
          <input type="password" value={form.password} onChange={setField("password")} required />
        </label>
        <label className="field">
          <span>تکرار رمز عبور *</span>
          <input type="password" value={form.password_confirm} onChange={setField("password_confirm")} required />
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
