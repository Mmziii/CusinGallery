import { Route, Routes, useLocation } from "react-router-dom";

import ErrorBoundary from "./components/ErrorBoundary.jsx";
import ProtectedRoute from "./components/ProtectedRoute.jsx";
import MainLayout from "./layouts/MainLayout.jsx";
import AccountLayout from "./pages/account/AccountLayout.jsx";
import AddressesPage from "./pages/account/AddressesPage.jsx";
import OrderDetailPage from "./pages/account/OrderDetailPage.jsx";
import OrdersPage from "./pages/account/OrdersPage.jsx";
import ProfilePage from "./pages/account/ProfilePage.jsx";
import ReviewsPage from "./pages/account/ReviewsPage.jsx";
import CartPage from "./pages/CartPage.jsx";
import CheckoutPage from "./pages/CheckoutPage.jsx";
import Home from "./pages/Home.jsx";
import LoginPage from "./pages/LoginPage.jsx";
import NotFound from "./pages/NotFound.jsx";
import PasswordResetConfirmPage from "./pages/PasswordResetConfirmPage.jsx";
import PasswordResetRequestPage from "./pages/PasswordResetRequestPage.jsx";
import PaymentResultPage from "./pages/PaymentResultPage.jsx";
import ProductDetailPage from "./pages/ProductDetailPage.jsx";
import RegisterPage from "./pages/RegisterPage.jsx";
import ShopPage from "./pages/ShopPage.jsx";
import WishlistPage from "./pages/WishlistPage.jsx";
import AboutPage from "./pages/info/AboutPage.jsx";
import ContactPage from "./pages/info/ContactPage.jsx";
import PrivacyPage from "./pages/info/PrivacyPage.jsx";
import ShippingReturnsPage from "./pages/info/ShippingReturnsPage.jsx";
import TermsPage from "./pages/info/TermsPage.jsx";

/**
 * Full storefront route tree. Everything lives under MainLayout;
 * authenticated flows (checkout, account) are wrapped in ProtectedRoute.
 */
function App() {
  const location = useLocation();

  return (
    // App-level catch-all for a shell/header/footer failure. MainLayout keeps
    // its narrower Outlet boundary so an ordinary route crash still leaves
    // the header available for recovery navigation.
    <ErrorBoundary resetKey={`${location.pathname}${location.search}`}>
      <Routes>
        <Route element={<MainLayout />}>
          <Route path="/" element={<Home />} />
          <Route path="/shop/" element={<ShopPage />} />
          <Route path="/products/:slug/" element={<ProductDetailPage />} />
          <Route path="/cart/" element={<CartPage />} />
          <Route path="/wishlist/" element={<ProtectedRoute><WishlistPage /></ProtectedRoute>} />
          <Route path="/checkout/" element={<ProtectedRoute><CheckoutPage /></ProtectedRoute>} />
          <Route path="/payment/result/:paymentId?/" element={<PaymentResultPage />} />
          {/* Trust pages (Phase E) -- public, listed in the footer and sitemap */}
          <Route path="/about/" element={<AboutPage />} />
          <Route path="/contact/" element={<ContactPage />} />
          <Route path="/shipping-returns/" element={<ShippingReturnsPage />} />
          <Route path="/terms/" element={<TermsPage />} />
          <Route path="/privacy/" element={<PrivacyPage />} />
          <Route path="/login/" element={<LoginPage />} />
          <Route path="/register/" element={<RegisterPage />} />
          <Route path="/password-reset/" element={<PasswordResetRequestPage />} />
          <Route path="/reset-password/confirm/" element={<PasswordResetConfirmPage />} />
          <Route
            path="/account/"
            element={<ProtectedRoute><AccountLayout /></ProtectedRoute>}
          >
            <Route index element={<ProfilePage />} />
            <Route path="orders/" element={<OrdersPage />} />
            <Route path="orders/:orderId/" element={<OrderDetailPage />} />
            <Route path="addresses/" element={<AddressesPage />} />
            <Route path="reviews/" element={<ReviewsPage />} />
          </Route>
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </ErrorBoundary>
  );
}

export default App;
