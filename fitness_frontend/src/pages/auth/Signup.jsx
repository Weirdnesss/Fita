import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../../context/AuthContext";
import { register } from "../../api/accounts";
import { clearTokens } from "../../api/client";
import VerifyEmailModal from "../../components/VerifyEmailModal";
import { ErrorBanner, extractErrorMessage } from "../../components/Status";

export default function Signup() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [showVerify, setShowVerify] = useState(false);

  const [form, setForm] = useState({
    firstName: "",
    lastName: "",
    email: "",
    password: "",
    confirmPassword: "",
  });

  const set = (field) => (e) => setForm((f) => ({ ...f, [field]: e.target.value }));

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      clearTokens(); // a stale token from an old session shouldn't ride along
      await register({
        email: form.email,
        firstName: form.firstName,
        lastName: form.lastName,
        password: form.password,
        confirmPassword: form.confirmPassword,
      });
      setShowVerify(true);
    } catch (err) {
      setError(extractErrorMessage(err, "Couldn't create your account. Check your details."));
    } finally {
      setSubmitting(false);
    }
  }

  // Called by the modal once the code checks out. The password is still in
  // this form's state, so we can log in right away and go to onboarding.
  async function handleVerified() {
    setShowVerify(false);
    try {
      await login({ email: form.email, password: form.password });
      navigate("/onboarding");
    } catch {
      setError("Your email is verified, but we couldn't sign you in automatically. Please use the Log In page.");
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-card" style={{ gap: 20 }}>
        <div style={{ textAlign: "center" }}>
          <div style={{ fontFamily: "var(--font-display)", fontSize: 26, color: "var(--chili)" }}>
            FITNESS ASSISTANT
          </div>
        </div>

        <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <h2>Create an account</h2>
          <div style={row2}>
            <div>
              <label>First name</label>
              <input required value={form.firstName} onChange={set("firstName")} placeholder="John" />
            </div>
            <div>
              <label>Last name</label>
              <input required value={form.lastName} onChange={set("lastName")} placeholder="Doe" />
            </div>
          </div>
          <div>
            <label>Email</label>
            <input type="email" required value={form.email} onChange={set("email")} placeholder="john.doe@example.com" />
          </div>
          <div>
            <label>Password</label>
            <input type="password" required minLength={8} value={form.password} onChange={set("password")} placeholder="At least 8 characters" />
          </div>
          <div>
            <label>Confirm password</label>
            <input type="password" required minLength={8} value={form.confirmPassword} onChange={set("confirmPassword")} />
          </div>
          <ErrorBanner message={error} />
          <button className="btn btn-primary btn-block" disabled={submitting}>
            {submitting ? "Creating account..." : "Continue"}
          </button>
          <p style={{ textAlign: "center", color: "var(--text-dim)", fontSize: 14 }}>
            Already have an account? <Link to="/login" style={{ color: "var(--chili)", fontWeight: 600 }}>Sign in</Link>
          </p>
        </form>
      </div>

      {showVerify && (
        <VerifyEmailModal
          email={form.email}
          password={form.password}
          onVerified={handleVerified}
          onEmailChanged={(newEmail) => setForm((f) => ({ ...f, email: newEmail }))}
          onClose={() => setShowVerify(false)}
        />
      )}
    </div>
  );
}

const row2 = { display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 };