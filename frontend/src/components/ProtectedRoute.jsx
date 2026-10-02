import { Navigate, useLocation } from "react-router-dom";

import useAuthStore from "../store/useAuthStore";
import { Spinner } from "./ui";

/**
 * Wraps authenticated-only routes. Waits for the initial /me/ probe to
 * finish before deciding anything, so a logged-in user refreshing the
 * page is never bounced through /login/ for a moment.
 */
function ProtectedRoute({ children }) {
  const { isAuthenticated, isLoading } = useAuthStore();
  const location = useLocation();

  if (isLoading) {
    return <Spinner label="در حال بررسی ورود…" />;
  }

  if (!isAuthenticated) {
    return <Navigate to="/login/" state={{ from: location.pathname + location.search }} replace />;
  }

  return children;
}

export default ProtectedRoute;
