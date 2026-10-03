import { Link } from "react-router-dom";

/**
 * Site footer (Phase E: trust pages, business info and the e-namad slot).
 *
 * ⚠ OWNER: replace the placeholder business details below (phone/address)
 * with the store's real information, and paste the e-namad (نماد اعتماد
 * الکترونیکی) embed code — the <script>/image snippet the enamad.ir panel
 * gives you — inside the marked div. Until then the slot shows a dashed
 * placeholder box so it is obvious something belongs there.
 */
function Footer() {
  return (
    <footer className="site-footer">
      <div className="container site-footer__grid">
        <div>
          <h3>کوزین گالری</h3>
          <p>
            فروشگاه آنلاین ظروف آشپزخانه، پخت‌وپز، بلور و کریستال و لوازم خانگی.
            خریدی مطمئن برای خانه‌ای زیباتر.
          </p>
          {/* ⚠ OWNER: اطلاعات واقعی کسب‌وکار را جایگزین کنید */}
          <p className="site-footer__contact">
            تلفن پشتیبانی: <span dir="ltr">+98 21 0000 0000</span>
            <br />
            آدرس: [آدرس واقعی فروشگاه را وارد کنید]
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
          {/* ⚠ OWNER: کد امبد نماد اعتماد الکترونیکی (e-namad) را از پنل
              enamad.ir کپی و اینجا جای‌گذاری کنید. تا آن زمان این جعبهٔ
              خط‌چین نمایش داده می‌شود. */}
          <div className="site-footer__enamad" aria-label="محل نماد اعتماد الکترونیکی">
            <span>محل نماد اعتماد الکترونیکی (e-namad)</span>
          </div>
        </div>
      </div>
      <div className="site-footer__bottom">
        <div className="container">© {new Date().getFullYear()} کوزین گالری</div>
      </div>
    </footer>
  );
}

export default Footer;
