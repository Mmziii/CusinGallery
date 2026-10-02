import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Small, generic "call an async function, track loading/error" hook.
 *
 * Extracted here (Phase 6) from what was originally a private helper
 * inside useCatalog.js (Phase 4) -- useOrders.js needed the exact same
 * data-fetching state machine, and duplicating it a third time would be
 * exactly the kind of repeated logic this project has consistently
 * avoided (see e.g. apps/products/pricing.py's "single mechanism, not
 * duplicated per view" precedent on the backend).
 *
 * Re-runs whenever `deps` changes, same contract as useEffect. Also
 * exposes a stable refetch() for imperative reloads (e.g. after a
 * mutation), which re-runs the SAME asyncFn without touching deps.
 */
export function useAsync(asyncFn, deps) {
  const [state, setState] = useState({ data: null, isLoading: true, error: null });
  const [reloadKey, setReloadKey] = useState(0);
  const fnRef = useRef(asyncFn);
  fnRef.current = asyncFn;

  useEffect(() => {
    let cancelled = false;
    setState((s) => ({ ...s, isLoading: true, error: null }));

    fnRef.current()
      .then((data) => {
        if (!cancelled) setState({ data, isLoading: false, error: null });
      })
      .catch((error) => {
        if (!cancelled) setState({ data: null, isLoading: false, error });
      });

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, reloadKey]);

  const refetch = useCallback(() => setReloadKey((key) => key + 1), []);

  return { ...state, refetch };
}
