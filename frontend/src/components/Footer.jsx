import { Link } from "react-router-dom";

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
          <h4>حساب کاربری</h4>
          <ul>
            <li><Link to="/login/">ورود</Link></li>
            <li><Link to="/register/">ثبت‌نام</Link></li>
            <li><Link to="/account/addresses/">آدرس‌های من</Link></li>
          </ul>
        </div>
        <div>
          <h4>تماس</h4>
          <p>وب‌سایت: cusin.ir</p>
        </div>
      </div>
      <div className="site-footer__bottom">
        <div className="container">© {new Date().getFullYear()} کوزین گالری</div>
      </div>
    </footer>
  );
}

export default Footer;
