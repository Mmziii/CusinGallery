import { useEffect, useState } from "react";

import { fetchSiteSettings } from "../services/siteApi";

/**
 * React binding for the singleton SiteSettings (Part 1). Returns {}
 * until loaded and {} forever if the endpoint fails -- every consumer
 * (footer, contact page, pickup info, floating contact button) must
 * render fine with missing values (they hide themselves then).
 */
export default function useSiteSettings() {
  const [settings, setSettings] = useState(null);

  useEffect(() => {
    let alive = true;
    fetchSiteSettings().then((data) => {
      if (alive) setSettings(data);
    });
    return () => {
      alive = false;
    };
  }, []);

  return settings || {};
}
