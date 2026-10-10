import PropTypes from "prop-types";
import { useEffect, useRef, useState } from "react";

import * as authApi from "../services/authApi";
import { fetchLocations } from "../services/siteApi";
import {
  MAX_PLOT_UNIT_LENGTH,
  digitInput,
  normalizePhone,
  normalizePlotUnit,
  validateAddressPayload,
} from "../utils/iranianFields";
import { toast } from "../utils/toast";
import { Alert, errorMessage } from "./ui";
import { normalizeApiError } from "../utils/apiError";

const OTHER_CITY = "__other__";

const FIELDS = [
  { key: "recipient_name", label: "نام گیرنده", required: true, maxLength: 150, autoComplete: "name" },
  { key: "phone", label: "شماره تماس", required: true, maxLength: 20, numeric: true, inputMode: "tel", autoComplete: "tel", helper: "موبایل (مانند 09123456789) یا ثابت با کد شهر (مانند 02112345678)" },
  { key: "province", label: "استان", required: true, maxLength: 100 },
  { key: "city", label: "شهر", required: true, maxLength: 100 },
  { key: "address", label: "آدرس کامل", required: true, textarea: true, autoComplete: "street-address" },
  { key: "postal_code", label: "کد پستی", required: true, maxLength: 10, numeric: true, inputMode: "numeric", autoComplete: "postal-code", helper: "کد پستی ۱۰ رقمی، بدون خط تیره" },
  // Part S5 item 6: both are required (starred) and numeric; «۰» is the
  // documented value for a customer with no unit.
  {
    key: "building_number",
    label: "پلاک",
    required: true,
    maxLength: 20,
    numeric: true,
    inputMode: "numeric",
    helper: "شمارهٔ پلاک ساختمان؛ فقط عدد",
  },
  {
    key: "unit",
    label: "واحد",
    required: true,
    maxLength: 20,
    numeric: true,
    inputMode: "numeric",
    helper: "اگر واحد ندارید عدد ۰ را وارد کنید",
  },
];

/**
 * Address form with two modes:
 *  - controlled-only (value/onChange): the parent owns the data (inline
 *    checkout address, edit-in-place); the parent may pass fieldErrors
 *    to display inline (Part S1 item 3);
 *  - saving (onSaved given): validates locally (mirroring the backend),
 *    submits, shows inline field errors, scrolls/focuses the first
 *    invalid field, and toasts on success.
 *
 * Part S1 item 3: Persian/Arabic digits are normalized to ASCII as the
 * user types in phone/postal code; optional unit/building_number accept
 * empty; failures are never silent.
 */
function AddressForm({ value = {}, onChange, onSaved, compact = false, initial = null, fieldErrors = {} }) {
  const [form, setForm] = useState(initial || {});
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [ownFieldErrors, setOwnFieldErrors] = useState({});
  const [provinces, setProvinces] = useState([]);
  const [otherCityMode, setOtherCityMode] = useState(false);
  const rootRef = useRef(null);

  const errors = fieldErrors && Object.keys(fieldErrors).length ? fieldErrors : ownFieldErrors;

  useEffect(() => {
    let active = true;
    fetchLocations().then((data) => {
      if (active) setProvinces(data?.provinces || []);
    }).catch(() => {});
    return () => {
      active = false;
    };
  }, []);

  const isControlled = Boolean(onChange);
  const current = isControlled ? value : form;

  const setField = (key, fieldValue) => {
    if (isControlled) {
      onChange({ ...value, [key]: fieldValue });
    } else {
      setForm((f) => ({ ...f, [key]: fieldValue }));
      // Editing a field clears its inline error immediately.
      setOwnFieldErrors((prev) => {
        if (!prev[key]) return prev;
        const next = { ...prev };
        delete next[key];
        return next;
      });
    }
  };

  const normalizeFor = (key, raw) => {
    if (key === "phone") return normalizePhone(raw).slice(0, 20);
    if (key === "postal_code") return digitInput(raw).slice(0, 10);
    // Part S5 item 6: Persian digits become ASCII as the user types.
    if (key === "unit" || key === "building_number") {
      return normalizePlotUnit(raw).slice(0, MAX_PLOT_UNIT_LENGTH);
    }
    return raw;
  };

  const focusFirstError = (errorMap) => {
    const firstKey = FIELDS.map((f) => f.key).find((key) => errorMap[key]);
    if (!firstKey) return;
    const el = rootRef.current?.querySelector(`#addr-${firstKey}`);
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "center" });
      el.focus({ preventScroll: true });
    }
  };

  const provinceEntry = provinces.find((p) => p.name === current.province) || null;
  const cityKnown = provinceEntry ? provinceEntry.cities.includes(current.city) : false;
  const showCityText = otherCityMode || (Boolean(current.city) && !cityKnown);
  const citySelectValue = showCityText ? OTHER_CITY : cityKnown ? current.city : "";

  // Controlled mode updates via a single onChange call, so compound edits
  // (province change resets city) must happen in one handler.
  const changeProvince = (name) => {
    const entry = provinces.find((p) => p.name === name);
    const city = entry && entry.cities.includes(current.city) ? current.city : "";
    setOtherCityMode(false);
    if (isControlled) {
      onChange({ ...value, province: name, city });
    } else {
      setForm((f) => ({ ...f, province: name, city }));
    }
  };

  const changeCitySelect = (selection) => {
    if (selection === OTHER_CITY) {
      setOtherCityMode(true);
      setField("city", "");
    } else {
      setOtherCityMode(false);
      setField("city", selection);
    }
  };

  const submit = async (event) => {
    event.preventDefault();
    setError(null);
    setOwnFieldErrors({});
    // Local validation first: identical rules to the backend, instant and
    // field-level -- no round-trip for mistakes we already know about.
    const localErrors = validateAddressPayload(form);
    if (Object.keys(localErrors).length > 0) {
      setOwnFieldErrors(localErrors);
      focusFirstError(localErrors);
      return;
    }
    setSaving(true);
    try {
      const payload = { ...form };
      // is_default only travels on create (the form shows the checkbox
      // there); a PATCH without it leaves the flag untouched.
      if (!initial?.id) payload.is_default = Boolean(form.is_default);
      const saved = initial?.id
        ? await authApi.updateAddress(initial.id, payload)
        : await authApi.createAddress(payload);
      toast(initial?.id ? "آدرس ویرایش شد." : "آدرس ذخیره شد.");
      if (onSaved) onSaved(saved);
    } catch (err) {
      const normalized = normalizeApiError(err);
      const apiFieldErrors = normalized.fieldErrors || {};
      if (Object.keys(apiFieldErrors).length > 0) {
        const flat = {};
        for (const [key, messages] of Object.entries(apiFieldErrors)) {
          flat[key] = Array.isArray(messages) ? messages.join(" ") : String(messages);
        }
        setOwnFieldErrors(flat);
        focusFirstError(flat);
      } else {
        setError(normalized);
      }
    } finally {
      setSaving(false);
    }
  };

  const renderFieldError = (key) =>
    errors[key] ? <span className="field__error" role="alert">{errors[key]}</span> : null;

  const renderProvince = (field) => {
    if (!provinces.length) {
      return (
        <input
          id={`addr-${field.key}`}
          type="text"
          maxLength={field.maxLength}
          value={current[field.key] || ""}
          onChange={(e) => setField(field.key, e.target.value)}
          aria-invalid={Boolean(errors[field.key])}
          className={errors[field.key] ? "is-invalid" : undefined}
        />
      );
    }
    return (
      <select
        id={`addr-${field.key}`}
        value={current.province || ""}
        onChange={(e) => changeProvince(e.target.value)}
        aria-invalid={Boolean(errors.province)}
        className={errors.province ? "is-invalid" : undefined}
      >
        <option value="">انتخاب استان…</option>
        {provinces.map((p) => (
          <option key={p.name} value={p.name}>
            {p.name}
          </option>
        ))}
      </select>
    );
  };

  const renderCity = (field) => {
    if (!provinces.length) {
      return (
        <input
          id={`addr-${field.key}`}
          type="text"
          maxLength={field.maxLength}
          value={current[field.key] || ""}
          onChange={(e) => setField(field.key, e.target.value)}
          aria-invalid={Boolean(errors[field.key])}
          className={errors[field.key] ? "is-invalid" : undefined}
        />
      );
    }
    const cities = provinceEntry ? provinceEntry.cities : [];
    return (
      <span className="field__city-combo">
        <select
          id={`addr-${field.key}`}
          value={citySelectValue}
          onChange={(e) => changeCitySelect(e.target.value)}
          disabled={!current.province && !showCityText}
          aria-invalid={Boolean(errors.city)}
          className={errors.city ? "is-invalid" : undefined}
        >
          <option value="">{current.province ? "انتخاب شهر…" : "ابتدا استان را انتخاب کنید"}</option>
          {cities.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
          <option value={OTHER_CITY}>شهر دیگر…</option>
        </select>
        {showCityText ? (
          <input
            type="text"
            maxLength={field.maxLength}
            placeholder="نام شهر خود را بنویسید"
            value={current.city || ""}
            onChange={(e) => setField("city", e.target.value)}
            className={errors.city ? "is-invalid" : undefined}
          />
        ) : null}
      </span>
    );
  };

  return (
    <form
      ref={rootRef}
      className={`address-form ${compact ? "address-form--compact" : ""}`}
      onSubmit={onSaved ? submit : undefined}
      noValidate
    >
      <div className="address-form__grid">
        {FIELDS.map((field) => (
          <label
            key={field.key}
            className={[
              "field",
              field.textarea ? "field--wide" : "",
              errors[field.key] ? "field--error" : "",
            ].filter(Boolean).join(" ")}
          >
            <span>
              {field.label}
              {field.required ? <span className="field__required" aria-hidden="true"> *</span> : null}
            </span>
            {field.key === "province" ? renderProvince(field) : null}
            {field.key === "city" ? renderCity(field) : null}
            {field.key !== "province" && field.key !== "city" && field.textarea ? (
              <textarea
                id={`addr-${field.key}`}
                rows={2}
                autoComplete={field.autoComplete}
                value={current[field.key] || ""}
                onChange={(e) => setField(field.key, e.target.value)}
                aria-invalid={Boolean(errors[field.key])}
              />
            ) : null}
            {field.key !== "province" && field.key !== "city" && !field.textarea ? (
              <input
                id={`addr-${field.key}`}
                type="text"
                maxLength={field.maxLength}
                inputMode={field.inputMode}
                autoComplete={field.autoComplete}
                dir={field.numeric ? "ltr" : undefined}
                value={current[field.key] || ""}
                onChange={(e) => setField(field.key, normalizeFor(field.key, e.target.value))}
                aria-invalid={Boolean(errors[field.key])}
              />
            ) : null}
            {field.helper ? <span className="muted field__hint">{field.helper}</span> : null}
            {renderFieldError(field.key)}
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

AddressForm.propTypes = {
  /** Controlled-mode values (parent owns the data, e.g. inline checkout). */
  value: PropTypes.object,
  /** Controlled-mode change handler; presence switches to controlled mode. */
  onChange: PropTypes.func,
  /** Saving mode: submit to the backend and hand the saved address back. */
  onSaved: PropTypes.func,
  /** Checkout layout: hides the is_default checkbox. */
  compact: PropTypes.bool,
  /** Existing address to edit (implies saving mode). */
  initial: PropTypes.object,
  /** Inline errors owned by the parent (controlled mode). */
  fieldErrors: PropTypes.object,
};

export default AddressForm;
