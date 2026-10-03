import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { Alert, errorMessage } from "../components/ui";
import * as authApi from "../services/authApi";
import { normalizeApiError } from "../utils/apiError";

/**
 * Password reset — step 2, in one of two modes (Phase D):
 *
 *   link mode  /reset-password/confirm/?uid=...&token=...
 *              Target of the emailed reset link; the user only supplies a
 *              new password (uid/token come from the backend-generated URL).
 *
 *   code mode  /reset-password/confirm/?mode=code&phone=...
 *              For phone-only accounts: the user enters the one-time code
 *              they received by SMS (plus their phone, prefilled and
 *              editable) and the new password. Codes expire (15 minutes
 *              by default), are single-use, and wrong/expired codes get
 *              the same generic Persian error as unknown phones.
 */
function PasswordResetConfirmPage() {
  const [searchParams] = useSearchParams();
  const mode = searchParams.get("mode") === "code" ? "code" : "link";
  const uid = searchParams.get("uid") || "";
  const token = searchParams.get("token") || "";

  const [phone, setPhone] = useState(searchParams.get("phone") || "");
  const [code, setCode] = useState("");
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
      const payload =
        mode === "code"
          ? {
              phone: phone.trim(),
              code: code.trim(),
              new_password: password,
              new_password_confirm: confirm,
            }
          : { uid, token, new_password: password, new_password_confirm: confirm };
      await authApi.confirmPasswordReset(payload);
      setDone(true);
    } catch (err) {
      setError(errorMessage(normalizeApiError(err)));
    } finally {
      setBusy(false);
    }
  };

  const linkModeBroken = mode === "link" && (!uid || !token);

  return (
    <div className="auth-page">
      <form className="auth-card" onSubmit={submit}>
        <h1>{mode === "code" ? "بازیابی با کد پیامک" : "تنظیم رمز عبور جدید"}</h1>
        {done ? (
          <>
            <Alert kind="success">رمز عبور شما تغییر کرد. اکنون می‌توانید وارد شوید.</Alert>
            <Link className="btn btn--primary btn--block" to="/login/">ورود</Link>
          </>
        ) : (
          <>
            {linkModeBroken ? (
              <Alert>لینک بازیابی معتبر نیست.</Alert>
            ) : (
              <>
                {mode === "code" ? (
                  <>
                    <p className="muted reset-help">
                      کد یک‌بارمصرفی که برایتان پیامک شد را وارد کنید. کد تا ۱۵ دقیقه اعتبار
                      دارد و فقط یک بار قابل استفاده است.
                    </p>
                    <label className="field">
                      <span>شماره موبایل</span>
                      <input
                        type="text"
                        value={phone}
                        onChange={(e) => setPhone(e.target.value)}
                        required
                        dir="ltr"
                      />
                    </label>
                    <label className="field">
                      <span>کد پیامک‌شده</span>
                      <input
                        type="text"
                        inputMode="numeric"
                        autoComplete="one-time-code"
                        maxLength={6}
                        value={code}
                        onChange={(e) => setCode(e.target.value)}
                        required
                        dir="ltr"
                      />
                    </label>
                  </>
                ) : null}
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
                {mode === "code" ? (
                  <Link className="link reset-help" to="/password-reset/">
                    کد را دریافت نکردید؟ ارسال دوباره
                  </Link>
                ) : null}
              </>
            )}
          </>
        )}
      </form>
    </div>
  );
}

export default PasswordResetConfirmPage;
