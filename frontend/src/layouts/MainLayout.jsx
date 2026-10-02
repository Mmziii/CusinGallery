import { Outlet } from "react-router-dom";

import Footer from "../components/Footer";
import Header from "../components/Header";

/**
 * Shared page shell: real header (search, nav, account, cart), content
 * outlet, and footer. Every route renders inside this unless a future
 * flow (e.g. a distraction-free checkout) needs its own layout.
 */
function MainLayout() {
  return (
    <div className="app-shell">
      <Header />

      <main className="app-shell__main">
        <div className="container">
          <Outlet />
        </div>
      </main>

      <Footer />
    </div>
  );
}

export default MainLayout;
