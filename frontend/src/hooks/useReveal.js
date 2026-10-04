import { useCallback, useEffect, useRef } from "react";

/**
 * Scroll-reveal (Part 3, hardened in Part R1).
 *
 * Bug fixed here: the original hook attached its IntersectionObserver in a
 * useEffect with [] deps, but several sections (ProductRow, ReviewHighlights,
 * categories, daily deals) mount the element carrying the ref ONLY AFTER the
 * data loads, so ref.current was null when the effect ran, the observer never
 * started and .reveal stayed at opacity 0 forever.
 *
 * The hook now returns a CALLBACK ref: React invokes it whenever the node
 * mounts/unmounts, so late-mounted nodes are observed too. Two fail-safes
 * guarantee content can never stay hidden:
 *   1. The hidden state is applied by CSS only when <html> carries the
 *      .js-reveal class, which this hook adds only when it actually sets up
 *      an observer (never for prefers-reduced-motion, never without JS).
 *   2. A 1.5 s timeout reveals the node even if the observer never fires.
 */
const FAILSAFE_MS = 1500;

function observerSupported() {
  return (
    typeof window !== "undefined" &&
    "IntersectionObserver" in window &&
    !(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches)
  );
}

export default function useReveal() {
  const cleanupRef = useRef(null);

  const detach = useCallback(() => {
    if (cleanupRef.current) {
      cleanupRef.current();
      cleanupRef.current = null;
    }
  }, []);

  // Callback ref: runs on mount of the node (whenever that happens) and with
  // null on unmount, which is what makes late-mounted sections work.
  const ref = useCallback(
    (node) => {
      detach();
      if (!node) return undefined;

      // Fail-safe #2: whatever else happens, reveal shortly after mount.
      const failsafe = window.setTimeout(() => node.classList.add("is-revealed"), FAILSAFE_MS);

      if (!observerSupported()) {
        // No JS observer (or reduced motion): never hide, show immediately.
        node.classList.add("is-revealed");
        cleanupRef.current = () => window.clearTimeout(failsafe);
        return undefined;
      }

      // Fail-safe #1 enabler: CSS hides .reveal only under html.js-reveal.
      document.documentElement.classList.add("js-reveal");

      const observer = new IntersectionObserver(
        (entries) => {
          for (const entry of entries) {
            if (entry.isIntersecting) {
              entry.target.classList.add("is-revealed");
              observer.unobserve(entry.target);
            }
          }
        },
        { rootMargin: "0px 0px -8% 0px", threshold: 0.08 }
      );
      observer.observe(node);

      cleanupRef.current = () => {
        window.clearTimeout(failsafe);
        observer.disconnect();
      };
      return undefined;
    },
    [detach]
  );

  useEffect(() => detach, [detach]);

  return ref;
}
