import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../../context/AuthContext";
import VerifyEmailModal from "../../components/VerifyEmailModal";
import { ErrorBanner, extractErrorMessage } from "../../components/Status";

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [showVerify, setShowVerify] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      await login({ email, password });
      navigate("/profile");
    } catch (err) {
      if (err?.response?.data?.code === "email_not_verified") {
        // Signed up but never finished verifying: finish it right here.
        setShowVerify(true);
      } else {
        setError(extractErrorMessage(err, "Couldn't sign in. Check your email and password."));
      }
    } finally {
      setSubmitting(false);
    }
  }

  // Only unverified accounts get here, i.e. people who signed up but closed
  // the modal, so they haven't done onboarding yet.
  async function handleVerified() {
    setShowVerify(false);
    try {
      await login({ email, password });
      navigate("/onboarding");
    } catch {
      setError("Your email is verified, but we couldn't sign you in automatically. Try logging in again.");
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        <div style={{ textAlign: "center" }}>
          <div style={{ fontFamily: "var(--font-display)", fontSize: 32, color: "var(--chili)" }}>
            FITNESS ASSISTANT
          </div>
          <p style={{ color: "var(--text-dim)", marginTop: 4 }}>Your personal fitness assistant</p>
        </div>

        <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <div>
            <label htmlFor="email">Email</label>
            <input id="email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@example.com" />
          </div>
          <div>
            <label htmlFor="password">Password</label>
            <input id="password" type="password" required value={password} onChange={(e) => setPassword(e.target.value)} placeholder="••••••••" />
          </div>
          <ErrorBanner message={error} />
          <button className="btn btn-primary btn-block" type="submit" disabled={submitting}>
            {submitting ? "Signing in..." : "Log In"}
          </button>
        </form>

        <p style={{ textAlign: "center", color: "var(--text-dim)", fontSize: 14 }}>
          Don't have an account? <Link to="/signup" style={{ color: "var(--chili)", fontWeight: 600 }}>Sign up</Link>
        </p>
      </div>

      {showVerify && (
        <VerifyEmailModal
          email={email}
          password={password}
          sendOnOpen
          onVerified={handleVerified}
          onEmailChanged={setEmail}
          onClose={() => {
            setShowVerify(false);
            setError("Your email isn't verified yet. Log in again to get a new code.");
          }}
        />
      )}
    </div>
  );
}