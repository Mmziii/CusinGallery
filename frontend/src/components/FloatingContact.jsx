import { useEffect, useState } from "react";

import Icon from "./Icon";
import useSiteSettings from "../hooks/useSiteSettings";

/**
 * Floating contact buttons (Part 3) built from SiteSettings. Hidden
 * entirely when the owner has configured no contact channel.
 * Part S2 item 7: also carries the «بازگشت به بالا» button, shown after
 * the page has scrolled down a bit.
 */
function FloatingContact() {
  const settings = useSiteSettings();
  const [showTop, setShowTop] = useState(false);
  const links = [];

  useEffect(() => {
    const onScroll = () => setShowTop(window.scrollY > 600);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  if (settings.whatsapp) {
    links.push([`https://wa.me/${settings.whatsapp.replace(/\D/g, "")}`, "chat", "گفتگو در واتس‌اپ"]);
  }
  if (settings.telegram) {
    links.push([
      settings.telegram.startsWith("http") ? settings.telegram : `https://t.me/${settings.telegram.replace("@", "")}`,
      "send",
      "پیام در تلگرام",
    ]);
  }
  if (settings.phone) {
    links.push([`tel:${settings.phone.replace(/\s/g, "")}`, "phone", "تماس تلفنی"]);
  }

  if (links.length === 0 && !showTop) return null;
  return (
    <div className="floating-contact">
      {showTop ? (
        <button
          type="button"
          className="back-to-top"
          aria-label="بازگشت به بالای صفحه"
          title="بازگشت به بالای صفحه"
          onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}
        >
          <Icon name="arrow-up" size={22} />
        </button>
      ) : null}
      {links.map(([href, icon, label]) => (
        <a key={label} href={href} target={href.startsWith("tel:") ? undefined : "_blank"} rel="noopener noreferrer" aria-label={label} title={label}>
          <Icon name={icon} size={22} />
        </a>
      ))}
    </div>
  );
}

export default FloatingContact;
