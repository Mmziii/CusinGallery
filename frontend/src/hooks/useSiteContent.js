import { useEffect, useState } from "react";

import { DEFAULT_CONTENT } from "../content/defaults";
import { fetchSiteContent } from "../services/siteApi";
import { applyThemeVariables } from "../utils/theme";

/**
 * Owner-editable storefront content + theme (Task 1/2).
 *
 * Starts with the current hard-coded texts (DEFAULT_CONTENT) so the first
 * render is never empty and a failed API call simply keeps today's site.
 * When the payload arrives it also applies the theme variables (a no-op in
 * production, where the Django shell already inlined them before paint) and
 * the uploaded favicon.
 */
export default function useSiteContent() {
  const [content, setContent] = useState(DEFAULT_CONTENT);

  useEffect(() => {
    let alive = true;
    fetchSiteContent().then((data) => {
      if (alive) setContent(data || DEFAULT_CONTENT);
    });
    return () => {
      alive = false;
    };
  }, []);

  useEffect(() => {
    if (content.theme?.css_variables) {
      applyThemeVariables(content.theme.css_variables);
    }
    const favicon = content.brand?.favicon;
    if (!favicon || typeof document === "undefined" || !document.head) return;
    let link = document.head.querySelector('link[rel="icon"]');
    if (!link) {
      link = document.createElement("link");
      link.setAttribute("rel", "icon");
      document.head.appendChild(link);
    }
    link.setAttribute("href", favicon);
  }, [content]);

  return content;
}
