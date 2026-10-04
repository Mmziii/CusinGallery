import { Link } from "react-router-dom";

import useSiteSettings from "../hooks/useSiteSettings";

/**
 * Site footer (Part 1: business info + e-namad come from the singleton
 * SiteSettings, editable in admin -- no more hardcoded placeholders in
 * the bundle; Part 3 will restyle it).
 *
 * e-namad: the owner pastes the embed snippet from the enamad.ir panel
 * into SiteSettings.enamad_html; until then the marked placeholder slot
 * stays visible so it is obvious something belongs there.
 */
function Footer() {
  const settings = useSiteSettings();

  return (
    <footer className="site-footer">
      <div className="container site-footer__grid">
        <div>
          <h3>کازین گالری</h3>
          <p>
            فروشگاه آنلاین ظروف آشپزخانه، پخت‌وپز، بلور و کریستال و لوازم خانگی.
            خریدی مطمئن برای خانه‌ای زیباتر.
          </p>
          <p className="site-footer__contact">
            {settings.phone ? (
              <>
                تلفن پشتیبانی: <span dir="ltr">{settings.phone}</span>
                <br />
              </>
            ) : null}
            {settings.address ? <>{settings.address}</> : null}
          </p>
        </div>
        <div>
          <h4>دسترسی سریع</h4>
          <ul>
            <li><Link to="/shop/">فروشگاه</Link></li>
            <li><Link to="/cart/">سبد خرید</Link></li>
            <li><Link to="/account/orders/">پیگیری سفارش</Link></li>
          </ul>
        </div>
        <div>
          <h4>راهنما و قوانین</h4>
          <ul>
            <li><Link to="/about/">دربارهٔ ما</Link></li>
            <li><Link to="/contact/">تماس با ما</Link></li>
            <li><Link to="/shipping-returns/">ارسال و مرجوعی</Link></li>
            <li><Link to="/terms/">شرایط و قوانین</Link></li>
            <li><Link to="/privacy/">حریم خصوصی</Link></li>
          </ul>
        </div>
        <div>
          <h4>نمادها و مجوزها</h4>
          {settings.enamad_html ? (
            <div
              className="site-footer__enamad-embed"
              // Owner-supplied embed snippet from the enamad.ir panel.
              // eslint-disable-next-line react/no-danger
              dangerouslySetInnerHTML={{ __html: settings.enamad_html }}
            />
          ) : (
            <div className="site-footer__enamad" aria-label="محل نماد اعتماد الکترونیکی">
              <span>محل نماد اعتماد الکترونیکی (e-namad)</span>
            </div>
          )}
        </div>
      </div>
      <div className="site-footer__bottom">
        <div className="container">© {new Date().getFullYear()} کازین گالری</div>
      </div>
    </footer>
  );
}

export default Footer;
