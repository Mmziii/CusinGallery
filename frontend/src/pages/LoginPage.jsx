import { usePageMeta } from "../hooks/usePageMeta";
import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";

import { Alert, errorMessage } from "../components/ui";
import useAuthStore from "../store/useAuthStore";

function LoginPage() {
  usePageMeta({ title: "ورود به حساب کاربری", path: "/login/" });
  const navigate = useNavigate();
  const location = useLocation();
  const { login, isLoading } = useAuthStore();

  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);

  const redirectTo = location.state?.from || "/";

  const submit = async (event) => {
    event.preventDefault();
    setError(null);
    const result = await login(identifier.trim(), password);
    if (result.success) {
      navigate(redirectTo, { replace: true });
    } else {
      setError(errorMessage(result.error));
    }
  };

  return (
    <div className="auth-page">
      <form className="auth-card" onSubmit={submit}>
        <h1>ورود به کازین گالری</h1>
        <label className="field">
          <span>شماره موبایل یا ایمیل</span>
          <input
            type="text"
            value={identifier}
            autoComplete="username"
            onChange={(e) => setIdentifier(e.target.value)}
            required
          />
        </label>
        <label className="field">
          <span>رمز عبور</span>
          <input
            type="password"
            value={password}
            autoComplete="current-password"
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </label>

        {error ? <Alert>{error}</Alert> : null}

        <button type="submit" className="btn btn--primary btn--block" disabled={isLoading}>
          {isLoading ? "در حال ورود…" : "ورود"}
        </button>

        <div className="auth-card__links">
          <Link to="/password-reset/">رمز عبور را فراموش کرده‌اید؟</Link>
          <Link to="/register/">حساب ندارید؟ ثبت‌نام</Link>
        </div>
      </form>
    </div>
  );
}

export default LoginPage;
