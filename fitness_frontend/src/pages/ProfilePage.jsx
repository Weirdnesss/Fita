import { useState } from "react";
import { useAuth } from "../context/AuthContext";
import { useNavigate } from "react-router-dom";
import PageHeader from "../components/PageHeader";
import WeightProgress from "../components/WeightProgress";
import { Loading } from "../components/Status";

export default function ProfilePage() {
  const { user, loading, logout } = useAuth();
  const navigate = useNavigate();
  const [showDetails, setShowDetails] = useState(false);

  if (loading) return <div className="page"><Loading /></div>;
  if (!user) return null;

  const profile = user.profile || {};
  const initials = `${user.first_name?.[0] || ""}${user.last_name?.[0] || ""}`.toUpperCase();

  function handleLogout() {
    logout();
    navigate("/login");
  }

  return (
    <div className="page">
      <PageHeader title="Profile" />

      <div className="card" style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
          <div style={avatarStyle}>{initials || "?"}</div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <h2 style={{ textTransform: "none" }}>{user.first_name} {user.last_name}</h2>
            <p style={{ color: "var(--text-dim)", fontSize: 13 }}>{user.email}</p>
          </div>
          <button
            className="btn btn-secondary"
            style={{ padding: "8px 14px", fontSize: 13, flexShrink: 0 }}
            onClick={() => navigate("/profile/edit")}
          >
            Edit
          </button>
        </div>

        <div style={{ display: "flex", justifyContent: "center" }}>
          <div style={{ width: "50%" }}>
            <StatBox label="BMI" value={profile.bmi ?? "--"} unit="" accent="turmeric" />
          </div>
        </div>
        </div>

      <WeightProgress />

      <div className="card">
        <button
          onClick={() => setShowDetails((s) => !s)}
          style={{ background: "none", border: "none", padding: 0, width: "100%", display: "flex", justifyContent: "space-between", alignItems: "center" }}
        >
          <h3>Details</h3>
          <span style={{ fontSize: 12, color: "var(--text-faint)" }}>{showDetails ? "Hide" : "Show"}</span>
        </button>
        {showDetails && (
          <div style={{ display: "flex", flexDirection: "column", gap: 12, marginTop: 12 }}>
            <DetailRow label="Primary goal" value={formatChoice(profile.primary_goal)} />
            <DetailRow label="Activity level" value={formatChoice(profile.activity_level)} />
            <DetailRow label="Height" value={profile.height_cm ? `${profile.height_cm} cm` : "--"} />
            <DetailRow label="Workout frequency" value={profile.workout_frequency ? `${profile.workout_frequency} / week` : "--"} />
            <DetailRow label="Workout location" value={formatChoice(profile.workout_location)} />
            {profile.medical_conditions && <DetailRow label="Medical conditions" value={profile.medical_conditions} />}
            {profile.food_allergies && <DetailRow label="Food allergies" value={profile.food_allergies} />}
          </div>
        )}
      </div>

      <button
        className="btn-ghost"
        style={{ background: "none", border: "none", color: "var(--text-faint)", fontSize: 13, textAlign: "center", padding: "8px 0" }}
        onClick={handleLogout}
      >
        Log Out
      </button>
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