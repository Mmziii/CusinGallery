import { NavLink, Outlet } from "react-router-dom";

/**
 * Account area shell: side navigation + nested route outlet.
 */
function AccountLayout() {
  return (
    <div className="account">
      <aside className="account__nav">
        <h2>حساب کاربری</h2>
        <NavLink to="/account/" end>پروفایل</NavLink>
        <NavLink to="/account/orders/">سفارش‌ها</NavLink>
        <NavLink to="/account/addresses/">آدرس‌ها</NavLink>
        <NavLink to="/account/reviews/">نظرات من</NavLink>
      </aside>
      <div className="account__content">
        <Outlet />
      </div>
    </div>
  );
}

export default AccountLayout;
