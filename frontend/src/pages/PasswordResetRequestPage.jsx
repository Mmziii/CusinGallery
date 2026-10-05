import { useState } from "react";
import { Link } from "react-router-dom";

import { Alert, errorMessage } from "../components/ui";
import * as authApi from "../services/authApi";
import { normalizeApiError } from "../utils/apiError";
import { toAsciiDigits } from "../utils/iranianFields";

/**
 * Password reset — step 1 (Phase D: complete for BOTH account shapes).
 *
 * The customer enters whatever they registered with (phone OR email) and
 * always gets the same generic answer (the backend never confirms or
 * denies that an account exists):
 *   - accounts WITH an email receive a reset LINK by email;
 *   - PHONE-ONLY accounts receive a one-time 6-digit CODE by SMS and use
 *     the «بازیابی با کد پیامک» path below (the confirm page in code
 *     mode: /reset-password/confirm/?mode=code&phone=...).
 */
function PasswordResetRequestPage() {
  const [identifier, setIdentifier] = useState("");
  const [submittedIdentifier, setSubmittedIdentifier] = useState("");
  const [sent, setSent] = useState(false);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const submit = async (event) => {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await authApi.requestPasswordReset(identifier.trim());
      setSubmittedIdentifier(identifier.trim());
      setSent(true);
    } catch (err) {
      setError(errorMessage(normalizeApiError(err)));
    } finally {
      setBusy(false);
    }
  };

  const codeModeHref = `/reset-password/confirm/?mode=code&phone=${encodeURIComponent(submittedIdentifier)}`;

  return (
    <div className="auth-page">
      <form className="auth-card" onSubmit={submit}>
        <h1>بازیابی رمز عبور</h1>
        {sent ? (
          <>
            <Alert kind="success">
              اگر حسابی با این مشخصات وجود داشته باشد، دستورالعمل بازیابی ارسال شده است.
            </Alert>
            <p className="muted reset-help">
              اگر حساب شما <strong>ایمیل</strong> دارد، لینک بازیابی برایتان ایمیل شد؛ آن را باز
              کنید و رمز جدید را بسازید.
              <br />
              اگر حساب شما <strong>فقط با شمارهٔ موبایل</strong> ثبت شده است، یک کد یک‌بارمصرف
              برایتان پیامک شد (اعتبار: ۱۵ دقیقه). کد را در صفحهٔ زیر وارد کنید:
            </p>
            <Link className="btn btn--primary btn--block" to={codeModeHref}>
              بازیابی با کد پیامک
            </Link>
            <button
              type="button"
              className="btn btn--outline btn--block"
              onClick={() => {
                setSent(false);
                setError(null);
              }}
            >
              ارسال دوباره / تغییر شماره یا ایمیل
            </button>
          </>
        ) : (
          <>
            <label className="field">
              <span>شماره موبایل یا ایمیل</span>
              <input
                type="text"
                dir="ltr"
                value={identifier}
                onChange={(e) => setIdentifier(toAsciiDigits(e.target.value))}
                required
              />
            </label>
            {error ? <Alert>{error}</Alert> : null}
            <button type="submit" className="btn btn--primary btn--block" disabled={busy}>
              {busy ? "در حال ارسال…" : "ارسال دستورالعمل بازیابی"}
            </button>
          </>
        )}
      </form>
    </div>
  );
}

export default PasswordResetRequestPage;
