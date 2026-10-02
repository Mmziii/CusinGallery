import { Route, Routes } from "react-router-dom";

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

/**
 * Full storefront route tree. Everything lives under MainLayout;
 * authenticated flows (checkout, account) are wrapped in ProtectedRoute.
 */
function App() {
  return (
    <Routes>
      <Route element={<MainLayout />}>
        <Route path="/" element={<Home />} />
        <Route path="/shop/" element={<ShopPage />} />
        <Route path="/products/:slug/" element={<ProductDetailPage />} />
        <Route path="/cart/" element={<CartPage />} />
        <Route path="/wishlist/" element={<ProtectedRoute><WishlistPage /></ProtectedRoute>} />
        <Route path="/checkout/" element={<ProtectedRoute><CheckoutPage /></ProtectedRoute>} />
        <Route path="/payment/result/:paymentId?/" element={<PaymentResultPage />} />
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
  );
}

export default App;
