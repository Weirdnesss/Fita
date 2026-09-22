import { useState } from "react";
import { useAuth } from "../context/AuthContext";
import { useNavigate } from "react-router-dom";
import PageHeader from "../components/PageHeader";
import WeightProgress from "../components/WeightProgress";
import { Loading } from "../components/Status";
import ConfirmDialog from "../components/ConfirmDialog";
import { isProfileIncomplete, formatHeight } from "../lib/profile";

export default function ProfilePage() {
  const { user, loading, logout } = useAuth();
  const navigate = useNavigate();
  const [confirmingLogout, setConfirmingLogout] = useState(false);

  if (loading) return <div className="page"><Loading /></div>;
  if (!user) return null;

  const profile = user.profile || {};
  const initials = `${user.first_name?.[0] || ""}${user.last_name?.[0] || ""}`.toUpperCase();
  const incomplete = isProfileIncomplete(profile);

  async function confirmLogout() {
    setConfirmingLogout(false);
    await logout();
    navigate("/login");
  }

  return (
    <div className="page page-narrow">
      <PageHeader title="Profile" />

      {incomplete && (
        <div className="card" style={{ background: "var(--chili-tint)", display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12 }}>
          <span style={{ fontSize: 13, color: "var(--chili)" }}>
            Finish setting up your profile so goals and routines can be personalized for you.
          </span>
          <button
            className="btn btn-primary"
            style={{ padding: "8px 14px", fontSize: 13, flexShrink: 0 }}
            onClick={() => navigate("/onboarding")}
          >
            Finish
          </button>
        </div>
      )}

      <div className="profile-grid">
        <div className="profile-col-left">
          <div className="card profile-card" style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
              <div style={avatarStyle}>{initials || "?"}</div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <h2 style={{ textTransform: "none" }}>{user.first_name} {user.last_name}</h2>
                <p style={{ color: "var(--text-dim)", fontSize: 13 }}>{user.email}</p>
              </div>
            </div>

            <div style={{ display: "flex", gap: 8 }}>
              <button
                className="btn btn-secondary"
                style={{ padding: "10px 14px", fontSize: 13, flex: 1 }}
                onClick={() => navigate("/profile/edit")}
              >
                Edit
              </button>
              <button
                className="btn btn-secondary"
                style={{ padding: "10px 14px", fontSize: 13, flex: 1, color: "var(--chili)" }}
                onClick={() => setConfirmingLogout(true)}
              >
                Log Out
              </button>
            </div>
          </div>
        </div>

        <div className="profile-col-right">
          <WeightProgress />
        </div>
      </div>

      <ConfirmDialog
        open={confirmingLogout}
        title="Log out"
        message="You'll need to sign back in to access your account. Continue?"
        confirmLabel="Log Out"
        onConfirm={confirmLogout}
        onCancel={() => setConfirmingLogout(false)}
      />
    </div>
  );
}

function StatBox({ label, value, unit, accent, onClick }) {
  return (
    <div
      style={{ textAlign: "center", padding: "10px 4px", background: "var(--bg-raised)", borderRadius: "var(--radius-sm)", cursor: onClick ? "pointer" : "default" }}
      onClick={onClick}
    >
      <div className="stat" style={{ fontSize: 18, color: accent ? `var(--${accent})` : "var(--text)" }}>
        {value}
        {unit && <span style={{ fontSize: 11, color: "var(--text-faint)" }}> {unit}</span>}
      </div>
      <div className="eyebrow" style={{ marginTop: 4 }}>{label}</div>
    </div>
  );
}

function DetailRow({ label, value }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 14 }}>
      <span style={{ color: "var(--text-dim)" }}>{label}</span>
      <span style={{ fontWeight: 500, textAlign: "right", maxWidth: "60%" }}>{value}</span>
    </div>
  );
}

function formatChoice(value) {
  if (!value) return "--";
  return value.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

const avatarStyle = {
  width: 56,
  height: 56,
  borderRadius: "50%",
  background: "var(--chili-tint)",
  color: "var(--chili)",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  fontWeight: 700,
  fontSize: 20,
  flexShrink: 0,
};