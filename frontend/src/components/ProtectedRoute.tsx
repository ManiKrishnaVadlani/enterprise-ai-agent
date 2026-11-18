import { Navigate, Outlet, useLocation } from "react-router";
import { useSession } from "../context/SessionContext";

export function ProtectedRoute() {
  const { authenticated } = useSession();
  const location = useLocation();
  return authenticated ? <Outlet /> : <Navigate to="/login" replace state={{ from: location.pathname }} />;
}
