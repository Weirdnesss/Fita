import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../../context/AuthContext";
import { ErrorBanner, extractErrorMessage } from "../../components/Status";

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      await login({ email, password });
      navigate("/profile");
    } catch (err) {
      setError(extractErrorMessage(err, "Couldn't sign in. Check your email and password."));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="page" style={{ justifyContent: "center", gap: 28 }}>
      <div style={{ textAlign: "center" }}>
        <div style={{ fontFamily: "var(--font-display)", fontSize: 32, color: "var(--chili)" }}>
          PRIMEFIT
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
  );
}
