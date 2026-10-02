import { useEffect, useState } from "react";

/**
 * Small, dependency-free responsive-breakpoint hook. Establishes the
 * hooks/ pattern for later phases (useCart, useAuth, useProducts, ...)
 * which will wrap src/services/* calls instead of touching axios directly
 * from components.
 */
export function useMediaQuery(query) {
  const [matches, setMatches] = useState(
    () => typeof window !== "undefined" && window.matchMedia(query).matches
  );

  useEffect(() => {
    const mediaQueryList = window.matchMedia(query);
    const listener = (event) => setMatches(event.matches);

    mediaQueryList.addEventListener("change", listener);
    return () => mediaQueryList.removeEventListener("change", listener);
  }, [query]);

  return matches;
}
