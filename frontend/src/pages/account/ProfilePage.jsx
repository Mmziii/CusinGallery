import PasswordHint from "../../components/PasswordHint.jsx";
import { useState } from "react";

import { Alert, errorMessage } from "../../components/ui";
import * as authApi from "../../services/authApi";
import useAuthStore from "../../store/useAuthStore";
import { normalizeApiError } from "../../utils/apiError";

function ProfilePage() {
  const { user, updateProfile } = useAuthStore();

  const [form, setForm] = useState({
    first_name: user?.first_name || "",
    last_name: user?.last_name || "",
    email: user?.email || "",
  });
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState(null);

  const [pw, setPw] = useState({ current_password: "", new_password: "", new_password_confirm: "" });
  const [pwMessage, setPwMessage] = useState(null);
  const [pwError, setPwError] = useState(null);

  const submitProfile = async (event) => {
    event.preventDefault();
    setSaved(false);
    setError(null);
    const result = await updateProfile(form);
    if (result.success) setSaved(true);
    else setError(errorMessage(result.error));
  };

  const submitPassword = async (event) => {
    event.preventDefault();
    setPwMessage(null);
    setPwError(null);
    try {
      await authApi.changePassword(pw);
      setPwMessage("رمز عبور با موفقیت تغییر کرد.");
      setPw({ current_password: "", new_password: "", new_password_confirm: "" });
    } catch (err) {
      setPwError(errorMessage(normalizeApiError(err)));
    }
  };

  return (
    <div className="profile-page">
      <h1>پروفایل</h1>
      <p className="muted">شماره موبایل (نام کاربری ورود): {user?.phone}</p>

      <form className="card" onSubmit={submitProfile}>
        <h2>اطلاعات حساب</h2>
        <div className="field-row">
          <label className="field">
            <span>نام</span>
            <input value={form.first_name} onChange={(e) => setForm((f) => ({ ...f, first_name: e.target.value }))} />
          </label>
          <label className="field">
            <span>نام خانوادگی</span>
            <input value={form.last_name} onChange={(e) => setForm((f) => ({ ...f, last_name: e.target.value }))} />
          </label>
        </div>
        <label className="field">
          <span>ایمیل</span>
          <input type="email" dir="ltr" value={form.email} onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))} />
        </label>
        {error ? <Alert>{error}</Alert> : null}
        {saved ? <Alert kind="success">ذخیره شد.</Alert> : null}
        <button type="submit" className="btn btn--primary">ذخیره تغییرات</button>
      </form>

      <form className="card" onSubmit={submitPassword}>
        <h2>تغییر رمز عبور</h2>
        <label className="field">
          <span>رمز عبور فعلی</span>
          <input type="password" value={pw.current_password} onChange={(e) => setPw((f) => ({ ...f, current_password: e.target.value }))} required />
        </label>
        <label className="field">
          <span>رمز عبور جدید</span>
          <input type="password" value={pw.new_password} onChange={(e) => setPw((f) => ({ ...f, new_password: e.target.value }))} required />
          <PasswordHint value={pw.new_password} />
        </label>
        <label className="field">
          <span>تکرار رمز عبور جدید</span>
          <input type="password" value={pw.new_password_confirm} onChange={(e) => setPw((f) => ({ ...f, new_password_confirm: e.target.value }))} required />
        </label>
        {pwError ? <Alert>{pwError}</Alert> : null}
        {pwMessage ? <Alert kind="success">{pwMessage}</Alert> : null}
        <button type="submit" className="btn btn--primary">تغییر رمز عبور</button>
      </form>
    </div>
  );
}

export default ProfilePage;
