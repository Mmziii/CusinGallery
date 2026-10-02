import { useState } from "react";

import * as authApi from "../services/authApi";
import { Alert, errorMessage } from "./ui";
import { normalizeApiError } from "../utils/apiError";

const FIELDS = [
  { key: "recipient_name", label: "نام گیرنده", required: true, maxLength: 150 },
  { key: "phone", label: "شماره تماس", required: true, maxLength: 20 },
  { key: "province", label: "استان", required: true, maxLength: 100 },
  { key: "city", label: "شهر", required: true, maxLength: 100 },
  { key: "address", label: "آدرس کامل", required: true, textarea: true },
  { key: "postal_code", label: "کد پستی", required: true, maxLength: 20 },
  { key: "unit", label: "واحد (اختیاری)", required: false, maxLength: 20 },
  { key: "building_number", label: "پلاک (اختیاری)", required: false, maxLength: 20 },
];

/**
 * Address form with two modes:
 *  - controlled-only (value/onChange): the parent owns the data (inline
 *    checkout address, edit-in-place);
 *  - saving (onSaved given): submits to the backend and hands the created
 *    address back to the parent.
 */
function AddressForm({ value = {}, onChange, onSaved, compact = false, initial = null }) {
  const [form, setForm] = useState(initial || {});
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  const isControlled = Boolean(onChange);
  const current = isControlled ? value : form;

  const setField = (key, fieldValue) => {
    if (isControlled) {
      onChange({ ...value, [key]: fieldValue });
    } else {
      setForm((f) => ({ ...f, [key]: fieldValue }));
    }
  };

  const submit = async (event) => {
    event.preventDefault();
    setError(null);
    setSaving(true);
    try {
      const payload = { ...form };
      // is_default only travels on create (the form shows the checkbox
      // there); a PATCH without it leaves the flag untouched.
      if (!initial?.id) payload.is_default = Boolean(form.is_default);
      const saved = initial?.id
        ? await authApi.updateAddress(initial.id, payload)
        : await authApi.createAddress(payload);
      if (onSaved) onSaved(saved);
    } catch (err) {
      setError(normalizeApiError(err));
    } finally {
      setSaving(false);
    }
  };

  return (
    <form className={`address-form ${compact ? "address-form--compact" : ""}`} onSubmit={onSaved ? submit : undefined}>
      <div className="address-form__grid">
        {FIELDS.map((field) => (
          <label key={field.key} className={field.textarea ? "field field--wide" : "field"}>
            <span>{field.label}{field.required ? " *" : ""}</span>
            {field.textarea ? (
              <textarea
                rows={2}
                value={current[field.key] || ""}
                onChange={(e) => setField(field.key, e.target.value)}
              />
            ) : (
              <input
                type="text"
                maxLength={field.maxLength}
                value={current[field.key] || ""}
                onChange={(e) => setField(field.key, e.target.value)}
              />
            )}
          </label>
        ))}
        {!compact && !initial ? (
          <label className="field checkbox">
            <input
              type="checkbox"
              checked={Boolean(current.is_default)}
              onChange={(e) => setField("is_default", e.target.checked)}
            />
            آدرس پیش‌فرض
          </label>
        ) : null}
      </div>

      {error ? <Alert>{errorMessage(error)}</Alert> : null}

      {onSaved ? (
        <button type="submit" className="btn btn--primary" disabled={saving}>
          {saving ? "در حال ذخیره…" : initial?.id ? "ذخیره تغییرات" : "افزودن آدرس"}
        </button>
      ) : null}
    </form>
  );
}

export default AddressForm;
