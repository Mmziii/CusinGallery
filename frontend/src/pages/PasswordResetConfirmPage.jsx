import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { Alert, errorMessage } from "../components/ui";
import * as authApi from "../services/authApi";
import { normalizeApiError } from "../utils/apiError";

/**
 * Target of the password-reset email link
 * (/reset-password/confirm/?uid=...&token=...). uid/token come from the
 * URL the backend itself generated; the user only supplies a new password.
 */
function PasswordResetConfirmPage() {
  const [searchParams] = useSearchParams();
  const uid = searchParams.get("uid") || "";
  const token = searchParams.get("token") || "";

  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [done, setDone] = useState(false);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const submit = async (event) => {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await authApi.confirmPasswordReset({
        uid,
        token,
        new_password: password,
        new_password_confirm: confirm,
      });
      setDone(true);
    } catch (err) {
      setError(errorMessage(normalizeApiError(err)));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="auth-page">
      <form className="auth-card" onSubmit={submit}>
        <h1>تنظیم رمز عبور جدید</h1>
        {done ? (
          <>
            <Alert kind="success">رمز عبور شما تغییر کرد. اکنون می‌توانید وارد شوید.</Alert>
            <Link className="btn btn--primary btn--block" to="/login/">ورود</Link>
          </>
        ) : (
          <>
            {!uid || !token ? (
              <Alert>لینک بازیابی معتبر نیست.</Alert>
            ) : (
              <>
                <label className="field">
                  <span>رمز عبور جدید</span>
                  <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
                </label>
                <label className="field">
                  <span>تکرار رمز عبور جدید</span>
                  <input type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} required />
                </label>
                {error ? <Alert>{error}</Alert> : null}
                <button type="submit" className="btn btn--primary btn--block" disabled={busy}>
                  {busy ? "در حال ذخیره…" : "ذخیره رمز جدید"}
                </button>
              </>
            )}
          </>
        )}
      </form>
    </div>
  );
}

export default PasswordResetConfirmPage;
