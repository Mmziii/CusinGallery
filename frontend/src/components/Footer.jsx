import { Link } from "react-router-dom";

import Icon from "./Icon";
import { SOCIAL_CHANNELS } from "../content/defaults";
import useSiteContent from "../hooks/useSiteContent";
import useSiteSettings from "../hooks/useSiteSettings";
import { faDigits, hoursRange, latinDigits } from "../utils/faDigits";

/**
 * Site footer (Task 3): every value now comes from the owner-editable
 * «محتوا و ظاهر سایت» page -- brand, about, contact details, working
 * hours, social channels, copyright and the e-namad embed.
 *
 * The storefront always renders something: until /site/content/ answers
 * (or if it never does) useSiteContent returns the texts this footer
 * shipped with. Contact rows also fall back to the legacy SiteSettings
 * endpoint so an older cached payload cannot blank them.
 */
function Footer() {
  const content = useSiteContent();
  const settings = useSiteSettings();
  const footer = content.footer || {};
  const brand = content.brand || {};

  const phones = footer.phones?.length ? footer.phones : settings.phone ? [settings.phone] : [];
  const email = footer.email || "";
  const address = footer.address || "";
  const workingHours = footer.working_hours || "";
  const socials = footer.socials || {};
  const socialLinks = SOCIAL_CHANNELS.filter(({ key }) => Boolean(socials[key]));
  const copyright =
    footer.copyright_text?.replace("{year}", String(new Date().getFullYear())) ||
    `© ${new Date().getFullYear()} ${brand.name || "کازین گالری"}`;

  return (
    <footer className="site-footer">
      <div className="container site-footer__grid">
        <div>
          <h3>{brand.name || "کازین گالری"}</h3>
          {brand.tagline ? <p className="site-footer__tagline">{brand.tagline}</p> : null}
          {footer.about ? <p>{footer.about}</p> : null}
          <address className="site-footer__contact">
            {phones.length ? (
              <p>
                تلفن پشتیبانی:{" "}
                {phones.map((phone, index) => (
                  <span key={phone}>
                    {index > 0 ? "، " : null}
                    <a dir="ltr" href={`tel:${latinDigits(phone).replace(/\s/g, "")}`}>
                      {faDigits(phone)}
                    </a>
                  </span>
                ))}
              </p>
            ) : null}
            {email ? (
              <p>
                ایمیل: <a dir="ltr" href={`mailto:${email}`}>{email}</a>
              </p>
            ) : null}
            {address ? <p>{faDigits(address)}</p> : null}
            {workingHours ? <p>ساعات پاسخگویی: {hoursRange(workingHours)}</p> : null}
          </address>
          {socialLinks.length ? (
            <ul className="site-footer__social" aria-label="شبکه‌های اجتماعی">
              {socialLinks.map(({ key, label, icon }) => (
                <li key={key}>
                  <a
                    href={socials[key]}
                    target="_blank"
                    rel="noopener noreferrer"
                    aria-label={label}
                    title={label}
                  >
                    <Icon name={icon} size={18} />
                  </a>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
        <div>
          <h4>{footer.quick_links_title || "دسترسی سریع"}</h4>
          <ul>
            <li><Link to="/shop/">فروشگاه</Link></li>
            <li><Link to="/cart/">سبد خرید</Link></li>
            <li><Link to="/account/orders/">پیگیری سفارش</Link></li>
          </ul>
        </div>
        <div>
          <h4>{footer.help_links_title || "راهنما و قوانین"}</h4>
          <ul>
            {/* Published info pages only -- an unpublished page must not be
                linked anywhere in the storefront. A null list means the
                API never answered, so the historical five links stay. */}
            {content.info_pages ? (
              content.info_pages.map((page) => (
                <li key={page.slug}>
                  <Link to={page.path}>{page.title}</Link>
                </li>
              ))
            ) : (
              <>
                <li><Link to="/about/">دربارهٔ ما</Link></li>
                <li><Link to="/contact/">تماس با ما</Link></li>
                <li><Link to="/shipping-returns/">ارسال و مرجوعی</Link></li>
                <li><Link to="/terms/">شرایط و قوانین</Link></li>
                <li><Link to="/privacy/">حریم خصوصی</Link></li>
              </>
            )}
          </ul>
        </div>
        <div>
          <h4>{footer.trust_title || "نمادها و مجوزها"}</h4>
          {footer.enamad_html ? (
            <div
              className="site-footer__enamad-embed"
              // Sanitised with an explicit allowlist in apps/core/sanitize.py
              // (both on save and when served); never raw owner input.
              // eslint-disable-next-line react/no-danger
              dangerouslySetInnerHTML={{ __html: footer.enamad_html }}
            />
          ) : (
            <div className="site-footer__enamad" aria-label="محل نماد اعتماد الکترونیکی">
              <span>محل نماد اعتماد الکترونیکی (e-namad)</span>
            </div>
          )}
        </div>
      </div>
      <div className="site-footer__bottom">
        <div className="container">{copyright}</div>
      </div>
    </footer>
  );
}

export default Footer;
