/**
 * The storefront's CURRENT hard-coded texts, used as the fallback when
 * /site/content/ is unreachable (or before it answers).
 *
 * These are intentionally the exact strings the React pages shipped with
 * before the texts became owner-editable, so a failed API call degrades to
 * today's site instead of an empty shell. The backend's data migration
 * seeds the same wording, which is what makes the switch invisible.
 */
export const DEFAULT_CONTENT = Object.freeze({
  brand: {
    name: "کازین گالری",
    tagline: "کازین گالری، خانهٔ ظروف دوست‌داشتنی",
    logo_light: "",
    logo_dark: "",
    favicon: "",
  },
  home: {
    heading: "کازین گالری؛ فروشگاه لوازم خانه و آشپزخانه",
    hero: {
      title: "کازین گالری، خانهٔ ظروف دوست‌داشتنی",
      subtitle:
        "ظروف آشپزخانه، بلور و کریستال و لوازم خانگی؛ انتخابی مطمئن برای خانه‌ای زیباتر.",
      button_text: "مشاهدهٔ فروشگاه",
      button_link: "/shop/",
    },
    sections: {
      categories: "دسته‌بندی‌ها",
      deals: "پیشنهاد امروز",
      featured: "محصولات منتخب",
      new: "جدیدترین محصولات",
      best_sellers: "پرفروش‌ترین‌ها",
      reviews: "از زبان خریداران",
    },
    story: {
      title: "کازین گالری؛ خانهٔ ظروف دوست‌داشتنی",
      text:
        "ما در کازین گالری باور داریم آشپزخانه قلب هر خانه است؛ به همین دلیل هر ظرف، " +
        "قابلمه و بلوری را خودمان پیش از عرضه بررسی می‌کنیم و با بسته‌بندی ضدضربه و " +
        "پشتیبانی پاسخگو به دست شما می‌رسانیم. انتخابی مطمئن، برای خانه‌ای زیباتر.",
    },
  },
  trust_strip: [
    { icon: "shield-check", label: "تضمین اصالت کالا و سلامت فیزیکی اجناس" },
    { icon: "box", label: "بسته‌بندی ضدضربهٔ کالا" },
    { icon: "truck", label: "ارسال به سراسر ایران" },
    { icon: "lock", label: "پرداخت امن اینترنتی" },
    { icon: "bolt-fast", label: "امکان تحویل اکسپرس" },
  ],
  footer: {
    about:
      "فروشگاه آنلاین ظروف آشپزخانه، پخت‌وپز، بلور و کریستال و لوازم خانگی. " +
      "خریدی مطمئن برای خانه‌ای زیباتر.",
    phones: [],
    email: "support@cusin.ir",
    address: "",
    working_hours: "",
    socials: {},
    enamad_html: "",
    copyright_text: "",
    quick_links_title: "دسترسی سریع",
    help_links_title: "راهنما و قوانین",
    trust_title: "نمادها و مجوزها",
  },
  // `links: null` means "the API did not provide a list" -- FloatingContact
  // then falls back to the SiteSettings-derived buttons it always built.
  floating: { enabled: true, links: null, show_scroll_top: true },
  theme: null,
  // null = "the API never answered": the footer then links to the five
  // historical pages. A real payload always carries the array; an empty
  // array means the owner unpublished every page, so nothing is linked.
  info_pages: null,
});

/**
 * Accept a payload only when it really is the site-content object; anything
 * else (empty `{}`, a 404 body, a proxy error page) becomes the fallback.
 * Sections are NOT deep-merged field by field: an owner who deliberately
 * clears a text must keep it empty.
 */
export function normalizeContent(raw) {
  if (!raw || typeof raw !== "object" || !raw.brand) return DEFAULT_CONTENT;
  return {
    brand: raw.brand,
    home: raw.home || DEFAULT_CONTENT.home,
    trust_strip: Array.isArray(raw.trust_strip)
      ? raw.trust_strip
      : DEFAULT_CONTENT.trust_strip,
    footer: raw.footer || DEFAULT_CONTENT.footer,
    floating: raw.floating || DEFAULT_CONTENT.floating,
    theme: raw.theme || null,
    info_pages: Array.isArray(raw.info_pages) ? raw.info_pages : null,
  };
}

/** Footer social channels in display order, with their Persian labels. */
export const SOCIAL_CHANNELS = Object.freeze([
  { key: "instagram", label: "اینستاگرام", icon: "instagram" },
  { key: "telegram", label: "تلگرام", icon: "send" },
  { key: "whatsapp", label: "واتس‌اپ", icon: "chat" },
  { key: "eitaa", label: "ایتا", icon: "send" },
  { key: "bale", label: "بله", icon: "send" },
]);
