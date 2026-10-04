import { useEffect, useRef } from "react";

/**
 * Scroll-reveal (Part 3): adds .is-revealed when the element enters the
 * viewport. CSS handles the transition and prefers-reduced-motion turns
 * the effect off (elements simply appear). Never blocks interaction:
 * if IntersectionObserver is missing the class is added immediately.
 */
export default function useReveal() {
  const ref = useRef(null);

  useEffect(() => {
    const node = ref.current;
    if (!node) return undefined;
    if (!("IntersectionObserver" in window)) {
      node.classList.add("is-revealed");
      return undefined;
    }
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
    return () => observer.disconnect();
  }, []);

  return ref;
}
