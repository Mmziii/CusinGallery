import PropTypes from "prop-types";
import { useEffect, useState } from "react";

import * as authApi from "../services/authApi";
import { fetchLocations } from "../services/siteApi";
import { Alert, errorMessage } from "./ui";
import { normalizeApiError } from "../utils/apiError";

const OTHER_CITY = "__other__";

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
 *
 * Part R3: province is a select over Iran's 31 provinces and city is a
 * dependent select with a "شهر دیگر" free-text escape hatch; if the
 * locations API is unreachable both degrade to plain text inputs so a
 * customer is never blocked.
 */
function AddressForm({ value = {}, onChange, onSaved, compact = false, initial = null }) {
  const [form, setForm] = useState(initial || {});
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [provinces, setProvinces] = useState([]);
  const [otherCityMode, setOtherCityMode] = useState(false);

  useEffect(() => {
    let active = true;
    fetchLocations().then((data) => {
      if (active) setProvinces(data?.provinces || []);
    });
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

  const renderProvince = (field) => {
    if (!provinces.length) {
      return (
        <input
          type="text"
          maxLength={field.maxLength}
          value={current[field.key] || ""}
          onChange={(e) => setField(field.key, e.target.value)}
        />
      );
    }
    return (
      <select value={current.province || ""} onChange={(e) => changeProvince(e.target.value)}>
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
          type="text"
          maxLength={field.maxLength}
          value={current[field.key] || ""}
          onChange={(e) => setField(field.key, e.target.value)}
        />
      );
    }
    const cities = provinceEntry ? provinceEntry.cities : [];
    return (
      <span className="field__city-combo">
        <select
          value={citySelectValue}
          onChange={(e) => changeCitySelect(e.target.value)}
          disabled={!current.province && !showCityText}
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
          />
        ) : null}
      </span>
    );
  };

  return (
    <form className={`address-form ${compact ? "address-form--compact" : ""}`} onSubmit={onSaved ? submit : undefined}>
      <div className="address-form__grid">
        {FIELDS.map((field) => (
          <label key={field.key} className={field.textarea ? "field field--wide" : "field"}>
            <span>{field.label}{field.required ? " *" : ""}</span>
            {field.key === "province" ? renderProvince(field) : null}
            {field.key === "city" ? renderCity(field) : null}
            {field.key !== "province" && field.key !== "city" && field.textarea ? (
              <textarea
                rows={2}
                value={current[field.key] || ""}
                onChange={(e) => setField(field.key, e.target.value)}
              />
            ) : null}
            {field.key !== "province" && field.key !== "city" && !field.textarea ? (
              <input
                type="text"
                maxLength={field.maxLength}
                value={current[field.key] || ""}
                onChange={(e) => setField(field.key, e.target.value)}
              />
            ) : null}
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
};

export default AddressForm;
