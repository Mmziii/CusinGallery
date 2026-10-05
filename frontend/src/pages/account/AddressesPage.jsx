import { useEffect, useState } from "react";

import AddressForm from "../../components/AddressForm";
import { Alert, EmptyState, Spinner, errorMessage } from "../../components/ui";
import * as authApi from "../../services/authApi";
import { normalizeApiError } from "../../utils/apiError";

function AddressesPage() {
  const [addresses, setAddresses] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState(null);
  const [actionError, setActionError] = useState(null);
  // Part S2 item 6: per-row busy flag so destructive buttons can neither
  // double-submit nor be spammed while a request is in flight.
  const [busyId, setBusyId] = useState(null);

  const load = () => {
    setIsLoading(true);
    authApi
      .listAddresses()
      .then(setAddresses)
      .catch((err) => setError(normalizeApiError(err)))
      .finally(() => setIsLoading(false));
  };

  useEffect(load, []);

  const handleDelete = async (id) => {
    // Part S2 item 6: destructive action needs confirmation.
    if (!window.confirm("این آدرس برای همیشه حذف شود؟")) return;
    setActionError(null);
    setBusyId(id);
    try {
      await authApi.deleteAddress(id);
      setAddresses((list) => list.filter((a) => a.id !== id));
    } catch (err) {
      setActionError(errorMessage(normalizeApiError(err)));
    } finally {
      setBusyId(null);
    }
  };

  const handleSetDefault = async (id) => {
    setActionError(null);
    setBusyId(id);
    try {
      await authApi.setDefaultAddress(id);
      setAddresses((list) => list.map((a) => ({ ...a, is_default: a.id === id })));
    } catch (err) {
      setActionError(errorMessage(normalizeApiError(err)));
    } finally {
      setBusyId(null);
    }
  };

  if (isLoading) return <Spinner label="در حال دریافت آدرس‌ها…" />;

  return (
    <div className="addresses-page">
      <div className="page-head">
        <h1>آدرس‌های من</h1>
        <button
          type="button"
          className="btn btn--primary"
          onClick={() => {
            setEditing(null);
            setShowForm(true);
          }}
        >
          + آدرس جدید
        </button>
      </div>

      {error ? <Alert>{errorMessage(error)}</Alert> : null}
      {actionError ? <Alert>{actionError}</Alert> : null}

      {showForm ? (
        <div className="card">
          <h2>{editing ? "ویرایش آدرس" : "آدرس جدید"}</h2>
          <AddressForm
            key={editing?.id || "new"}
            initial={editing || null}
            onSaved={() => {
              setShowForm(false);
              setEditing(null);
              load();
            }}
          />
          <button type="button" className="link" onClick={() => setShowForm(false)}>انصراف</button>
        </div>
      ) : null}

      {!addresses.length && !showForm ? (
        <EmptyState title="هنوز آدرسی ثبت نکرده‌اید." />
      ) : (
        <div className="address-list">
          {addresses.map((address) => (
            <div key={address.id} className="address-card address-card--static">
              <div>
                <strong>{address.recipient_name}</strong>
                {address.is_default ? <em className="address-card__default">پیش‌فرض</em> : null}
                <p>
                  {address.province}، {address.city}، {address.address}
                  {address.unit ? `، واحد ${address.unit}` : ""}
                </p>
                <p className="muted">کد پستی: {address.postal_code} — تماس: {address.phone}</p>
              </div>
              <div className="address-card__actions">
                {!address.is_default ? (
                  <button
                    type="button"
                    className="btn btn--outline btn--sm"
                    disabled={busyId === address.id}
                    onClick={() => handleSetDefault(address.id)}
                  >
                    پیش‌فرض
                  </button>
                ) : null}
                <button
                  type="button"
                  className="btn btn--outline btn--sm"
                  onClick={() => {
                    setEditing(address);
                    setShowForm(true);
                  }}
                >
                  ویرایش
                </button>
                <button
                  type="button"
                  className="link-danger"
                  disabled={busyId === address.id}
                  onClick={() => handleDelete(address.id)}
                >
                  {busyId === address.id ? "…" : "حذف"}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default AddressesPage;
