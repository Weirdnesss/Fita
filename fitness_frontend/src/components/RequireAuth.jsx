import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { Loading } from "./Status";
import { isProfileIncomplete } from "../lib/profile";

export default function RequireAuth({ children }) {
  const { user, loading } = useAuth();
  const location = useLocation();

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

  // Signup's 3-step wizard only keeps its step in local React state, not
  // persisted anywhere -- so if the app is closed/killed between Step 1
  // (account created + logged in) and finishing Step 2/3, reopening it
  // leaves a fully authenticated user with an incomplete profile. Other
  // pages assume this data exists (nutrition goal calculation, workout
  // generation, BMI) and degrade rather than guide the user back, so
  // send them to /profile instead -- it has both the weight-log entry
  // point and the Edit link for everything else. Exempt /profile and
  // /profile/edit themselves so this can't become a redirect loop.
  const onProfilePages = location.pathname === "/profile" || location.pathname === "/profile/edit";
  if (!onProfilePages && isProfileIncomplete(user.profile)) {
    return <Navigate to="/profile" replace />;
  }

  return children;
}