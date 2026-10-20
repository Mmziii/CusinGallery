import PropTypes from "prop-types";
import { useId, useRef } from "react";

import Portal from "./Portal";
import useFocusTrap from "../hooks/useFocusTrap";

/**
 * The storefront's ONE confirmation dialog (PR 20).
 *
 * It replaces every native `window.confirm()` call site: those read as
 * "193.5.44.126 says" on iPhone, inherit none of the brand, and cannot
 * be styled, trapped or announced properly. This is a real modal
 * alertdialog instead -- rendered through the body Portal (so no
 * ancestor can capture it), focus-trapped, Escape = cancel, and on
 * close focus returns to whatever opened it.
 *
 * The component itself stays MOUNTED and renders nothing while closed:
 * useFocusTrap restores focus when its `active` flag flips false, not
 * on unmount, so keeping the hook owner alive is what puts the focus
 * back on the row the shopper was editing.
 *
 * Pair it with `useConfirm()` (hooks/useConfirm.jsx), which wraps this
 * in a Promise<boolean>; nothing else should render one directly.
 */
function ConfirmDialog({
  open,
  label = "تأیید حذف",
  message,
  confirmLabel = "حذف",
  cancelLabel = "انصراف",
  onConfirm,
  onCancel,
}) {
  const boxRef = useRef(null);
  const messageId = useId();

  // Focus trap + Escape(cancel) + restore. The trap focuses the first
  // focusable element in the box -- «انصراف» is deliberately first in
  // the DOM, so a destructive «حذف» is never one stray Enter away.
  useFocusTrap(boxRef, open, onCancel);

  if (!open) return null;

  return (
    <Portal>
      <div className="confirm-dialog">
        <div className="confirm-dialog__backdrop" aria-hidden="true" onClick={onCancel} />
        <div
          className="confirm-dialog__box"
          role="alertdialog"
          aria-modal="true"
          aria-label={label}
          aria-describedby={messageId}
          ref={boxRef}
        >
          <p className="confirm-dialog__message" id={messageId}>
            {message}
          </p>
          <div className="confirm-dialog__actions">
            <button type="button" className="btn btn--outline" onClick={onCancel}>
              {cancelLabel}
            </button>
            <button type="button" className="btn btn--danger" onClick={onConfirm}>
              {confirmLabel}
            </button>
          </div>
        </div>
      </div>
    </Portal>
  );
}

ConfirmDialog.propTypes = {
  open: PropTypes.bool.isRequired,
  label: PropTypes.string,
  message: PropTypes.string,
  confirmLabel: PropTypes.string,
  cancelLabel: PropTypes.string,
  onConfirm: PropTypes.func.isRequired,
  onCancel: PropTypes.func.isRequired,
};

export default ConfirmDialog;
