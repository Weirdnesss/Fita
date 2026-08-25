import { Navigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { Loading } from "./Status";

export default function RequireAuth({ children }) {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div className="page" style={{ justifyContent: "center", alignItems: "center" }}>
        <Loading />
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  return children;
}
