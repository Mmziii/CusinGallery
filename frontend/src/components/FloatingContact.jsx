import useSiteSettings from "../hooks/useSiteSettings";

/**
 * Floating contact buttons (Part 3) built from SiteSettings. Hidden
 * entirely when the owner has configured no contact channel.
 */
function FloatingContact() {
  const settings = useSiteSettings();
  const links = [];

  if (settings.whatsapp) {
    links.push([`https://wa.me/${settings.whatsapp.replace(/\D/g, "")}`, "✆", "گفتگو در واتس‌اپ"]);
  }
  if (settings.telegram) {
    links.push([
      settings.telegram.startsWith("http") ? settings.telegram : `https://t.me/${settings.telegram.replace("@", "")}`,
      "✈",
      "پیام در تلگرام",
    ]);
  }
  if (settings.phone) {
    links.push([`tel:${settings.phone.replace(/\s/g, "")}`, "☎", "تماس تلفنی"]);
  }

  if (links.length === 0) return null;
  return (
    <div className="floating-contact">
      {links.map(([href, icon, label]) => (
        <a key={label} href={href} target={href.startsWith("tel:") ? undefined : "_blank"} rel="noopener noreferrer" aria-label={label} title={label}>
          <span aria-hidden="true">{icon}</span>
        </a>
      ))}
    </div>
  );
}

export default FloatingContact;
