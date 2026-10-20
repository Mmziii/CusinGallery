import { useCallback, useEffect, useRef, useState } from "react";

import ConfirmDialog from "../components/ConfirmDialog";

/**
 * The async drop-in for `window.confirm()` (PR 20).
 *
 *   const { confirm, dialog } = useConfirm();
 *   if (!(await confirm("این کالا از سبد خرید حذف شود؟"))) return;
 *   ...
 *   return (<>... {dialog} </>);
 *
 * `confirm(...)` resolves `true` only when the shopper picks the danger
 * button; «انصراف», Escape, a backdrop tap, a second confirm request or
 * the owner unmounting all resolve `false`, so a destructive action can
 * never slip through on an ambiguous path. `dialog` is the styled,
 * focus-trapped alertdialog (ConfirmDialog via the body Portal) and
 * must be rendered somewhere in the owner's tree.
 */
export function useConfirm() {
  const [request, setRequest] = useState(null);
  const requestRef = useRef(null);

  const settle = useCallback((value) => {
    const pending = requestRef.current;
    requestRef.current = null;
    setRequest(null);
    pending?.resolve(value);
  }, []);

  const confirm = useCallback(
    (message, options = {}) => {
      // One question at a time: a new request cancels the one on screen.
      requestRef.current?.resolve(false);
      return new Promise((resolve) => {
        const pending = { message, ...options, resolve };
        requestRef.current = pending;
        setRequest(pending);
      });
    },
    []
  );

  // If the owner unmounts mid-question, the awaiting handler must get a
  // "no" instead of hanging forever.
  useEffect(
    () => () => {
      requestRef.current?.resolve(false);
      requestRef.current = null;
    },
    []
  );

  const dialog = (
    <ConfirmDialog
      open={Boolean(request)}
      label={request?.label}
      message={request?.message}
      confirmLabel={request?.confirmLabel}
      cancelLabel={request?.cancelLabel}
      onConfirm={() => settle(true)}
      onCancel={() => settle(false)}
    />
  );

  return { confirm, dialog };
}

export default useConfirm;
