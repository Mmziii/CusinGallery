import { useState } from "react";

import { Alert, errorMessage } from "../components/ui";
import * as authApi from "../services/authApi";
import { normalizeApiError } from "../utils/apiError";

function PasswordResetRequestPage() {
  const [identifier, setIdentifier] = useState("");
  const [sent, setSent] = useState(false);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const submit = async (event) => {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await authApi.requestPasswordReset(identifier.trim());
      setSent(true);
    } catch (err) {
      setError(errorMessage(normalizeApiError(err)));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="auth-page">
      <form className="auth-card" onSubmit={submit}>
        <h1>بازیابی رمز عبور</h1>
        {sent ? (
          <Alert kind="success">
            اگر حسابی با این مشخصات وجود داشته باشد، دستورالعمل بازیابی ارسال شده است.
          </Alert>
        ) : (
          <>
            <label className="field">
              <span>شماره موبایل یا ایمیل</span>
              <input type="text" value={identifier} onChange={(e) => setIdentifier(e.target.value)} required />
            </label>
            {error ? <Alert>{error}</Alert> : null}
            <button type="submit" className="btn btn--primary btn--block" disabled={busy}>
              {busy ? "در حال ارسال…" : "ارسال لینک بازیابی"}
            </button>
          </>
        )}
      </form>
    </div>
  );
}

export default PasswordResetRequestPage;
