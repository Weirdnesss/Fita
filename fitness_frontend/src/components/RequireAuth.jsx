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

  // Onboarding (the post-signup profile setup) keeps its step in local
  // React state, not persisted anywhere -- so if the app is closed/killed
  // partway through it, reopening it leaves a fully authenticated user
  // with an incomplete profile. Other pages assume this data exists
  // (nutrition goal calculation, workout generation, BMI) and degrade
  // rather than guide the user back, so send them to /onboarding instead.
  // /profile and /profile/edit stay exempt too -- someone who later
  // blanks a field via Edit Profile can still reach both directly rather
  // than being funneled back through onboarding from scratch.
  const exemptPaths = ["/profile", "/profile/edit", "/onboarding"];
  const onExemptPage = exemptPaths.includes(location.pathname);
  if (!onExemptPage && isProfileIncomplete(user.profile)) {
    return <Navigate to="/onboarding" replace />;
  }

  return children;
}