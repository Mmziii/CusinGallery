import { useLocation } from "react-router-dom";
import { useEffect, useState } from "react";

import Icon from "./Icon";
import { latinDigits } from "../utils/faDigits";
import useSiteContent from "../hooks/useSiteContent";
import useSiteSettings from "../hooks/useSiteSettings";

/**
 * Floating contact buttons (Task 3).
 *
 * The owner picks which channels float (whatsapp / telegram / phone /
 * instagram) on the «محتوا و ظاهر سایت» page; the backend resolves every
 * handle into a real URL, so this component just renders the list.
 * When the payload has no links (or the request failed), it falls back to
 * the SiteSettings-derived buttons it has always built.
 *
 * Part S2 item 7: also carries «بازگشت به بالا», shown after scrolling.
 */
function FloatingContact() {
  const content = useSiteContent();
  const settings = useSiteSettings();
  const { pathname } = useLocation();
  const [showTop, setShowTop] = useState(false);
  const [mobileExpanded, setMobileExpanded] = useState(false);

  useEffect(() => {
    const onScroll = () => setShowTop(window.scrollY > 600);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  const floating = content.floating || {};
  let links = Array.isArray(floating.links) ? floating.links : [];

  if (!Array.isArray(floating.links)) {
    // Legacy fallback: build the buttons straight from SiteSettings.
    links = [];
    if (settings.whatsapp) {
      links.push({
        key: "whatsapp",
        href: `https://wa.me/${settings.whatsapp.replace(/\D/g, "")}`,
        icon: "chat",
        label: "گفتگو در واتس‌اپ",
      });
    }
    if (settings.telegram) {
      links.push({
        key: "telegram",
        href: settings.telegram.startsWith("http")
          ? settings.telegram
          : `https://t.me/${settings.telegram.replace("@", "")}`,
        icon: "send",
        label: "پیام در تلگرام",
      });
    }
    if (settings.phone) {
      links.push({
        key: "phone",
        href: `tel:${latinDigits(settings.phone).replace(/\s/g, "")}`,
        icon: "phone",
        label: "تماس تلفنی",
      });
    }
  }

  const enabled = floating.enabled !== false;
  const showBackToTop = floating.show_scroll_top !== false && showTop;

  if (!enabled) return null;
  if (pathname.startsWith("/products/")) return null;
  if (pathname.startsWith("/cart/") || pathname === "/cart" || pathname.startsWith("/checkout")) return null;
  if (links.length === 0 && !showBackToTop) return null;

  return (
    <div className={`floating-contact${mobileExpanded ? " floating-contact--expanded" : ""}`}>
      {showBackToTop ? (
        <button
          type="button"
          className="back-to-top"
          aria-label="بازگشت به بالای صفحه"
          title="بازگشت به بالای صفحه"
          onClick={() => window.scrollTo({ top: 0, behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth" })}
        >
          <Icon name="arrow-up" size={22} />
        </button>
      ) : null}
      {links.map(({ key, href, icon, label }) => (
        <a
          key={key || href}
          href={href}
          target={href.startsWith("tel:") ? undefined : "_blank"}
          rel="noopener noreferrer"
          aria-label={label}
          title={label}
        >
          <Icon name={icon} size={22} />
        </a>
      ))}
      {links.length ? (
        <button
          type="button"
          className="floating-contact__toggle"
          aria-label={mobileExpanded ? "بستن راه‌های تماس" : "نمایش راه‌های تماس"}
          aria-expanded={mobileExpanded}
          onClick={() => setMobileExpanded((expanded) => !expanded)}
        >
          <Icon name={mobileExpanded ? "close" : "chat"} size={20} />
        </button>
      ) : null}
    </div>
  );
}

export default FloatingContact;
