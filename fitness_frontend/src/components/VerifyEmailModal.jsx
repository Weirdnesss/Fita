import { useEffect, useRef, useState } from "react";
import { changeEmail, resendVerification, verifyEmail } from "../api/accounts";
import { ErrorBanner } from "./Status";

const msg = (err, fallback) =>
  err?.response?.data?.error || err?.response?.data?.detail || fallback;

export default function VerifyEmailModal({
  email,
  password,
  onVerified,
  onEmailChanged,
  onClose,
  sendOnOpen = false, // true when opened from Login: no fresh code exists yet
}) {
  const [mode, setMode] = useState("verify"); // verify | change
  const [code, setCode] = useState("");
  const [newEmail, setNewEmail] = useState("");
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");
  const [busy, setBusy] = useState(false);
  const [cooldown, setCooldown] = useState(30);
  const sentOnOpen = useRef(false);

  useEffect(() => {
    if (!sendOnOpen || sentOnOpen.current) return;
    sentOnOpen.current = true; // guards React StrictMode's double effect in dev
    resendVerification(email)
      .then(() => setInfo(`We sent a new code to ${email}.`))
      .catch((err) => setError(msg(err, "Couldn't send a code right now. Try Resend in a moment.")));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (cooldown <= 0) return;
    const t = setTimeout(() => setCooldown((c) => c - 1), 1000);
    return () => clearTimeout(t);
  }, [cooldown]);

  async function handleVerify(e) {
    e.preventDefault();
    if (code.length !== 6) {
      setError("Enter the 6-digit code.");
      return;
    }
    setError("");
    setBusy(true);
    try {
      await verifyEmail({ email, code });
      await onVerified();
    } catch (err) {
      setError(msg(err, "Couldn't verify the code. Try again."));
    } finally {
      setBusy(false);
    }
  }

  async function handleResend() {
    setError("");
    setInfo("");
    try {
      await resendVerification(email);
      setInfo("A new code was sent.");
      setCode("");
      setCooldown(30);
    } catch (err) {
      setError(msg(err, "Couldn't resend right now. Try again later."));
    }
  }

  async function handleChange(e) {
    e.preventDefault();
    setError("");
    setInfo("");
    setBusy(true);
    try {
      const data = await changeEmail({ email, password, newEmail });
      onEmailChanged(data.email || newEmail);
      setMode("verify");
      setCode("");
      setNewEmail("");
      setInfo("Code sent to your new email.");
      setCooldown(30);
    } catch (err) {
      setError(msg(err, "Couldn't change your email."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={overlay} role="dialog" aria-modal="true">
      <div className="auth-card" style={card}>
        {mode === "verify" ? (
          <form key="verify" onSubmit={handleVerify} style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <h2>Verify your email</h2>
            <p style={{ color: "var(--text-dim)", fontSize: 14 }}>
              We sent a 6-digit code to <strong>{email}</strong>. It expires in 10 minutes.
            </p>
            <input
              autoFocus
              inputMode="numeric"
              autoComplete="one-time-code"
              maxLength={6}
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
              placeholder="000000"
              style={{ textAlign: "center", fontSize: 24, letterSpacing: 8 }}
            />
            <ErrorBanner message={error} />
            {info && <p style={{ fontSize: 14 }}>{info}</p>}
            <button type="submit" className="btn btn-primary btn-block" disabled={busy}>
              {busy ? "Verifying..." : "Verify"}
            </button>
            <button
              type="button"
              className="btn btn-block"
              onClick={handleResend}
              disabled={cooldown > 0}
            >
              {cooldown > 0 ? `Resend code in ${cooldown}s` : "Resend code"}
            </button>
            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <button
                type="button"
                style={linkBtn}
                onClick={() => {
                  setMode("change");
                  setError("");
                  setInfo("");
                }}
              >
                Wrong email?
              </button>
              <button type="button" style={linkBtn} onClick={onClose}>
                Close
              </button>
            </div>
          </form>
        ) : (
          <form key="change" onSubmit={handleChange} style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <h2>Change email</h2>
            <p style={{ color: "var(--text-dim)", fontSize: 14 }}>
              Currently <strong>{email}</strong>. We'll send a new code to the address you enter.
            </p>
            <input
              autoFocus
              type="email"
              required
              value={newEmail}
              onChange={(e) => setNewEmail(e.target.value)}
              placeholder="new.email@example.com"
            />
            <ErrorBanner message={error} />
            <button type="submit" className="btn btn-primary btn-block" disabled={busy}>
              {busy ? "Sending..." : "Send new code"}
            </button>
            <button
              type="button"
              style={linkBtn}
              onClick={() => {
                setMode("verify");
                setError("");
              }}
            >
              Back
            </button>
          </form>
        )}
      </div>
    </div>
  );
}

const overlay = {
  position: "fixed",
  inset: 0,
  background: "rgba(0,0,0,0.6)",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  padding: 16,
  zIndex: 1000,
};

const linkBtn = {
  background: "none",
  border: "none",
  padding: 0,
  cursor: "pointer",
  color: "var(--chili)",
  fontWeight: 600,
  fontSize: 14,
};

const card = {
  gap: 16,
  maxWidth: 400,
  width: "100%",
  background: "var(--bg-card, var(--surface, #1c1c1e))",
  border: "1px solid var(--border, rgba(255,255,255,0.1))",
  borderRadius: 16,
  padding: 24,
  maxHeight: "90vh",
  overflowY: "auto", // keeps the buttons reachable when the phone keyboard opens
  boxShadow: "0 10px 40px rgba(0,0,0,0.5)",
};