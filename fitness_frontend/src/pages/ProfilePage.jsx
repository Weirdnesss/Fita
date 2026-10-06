import { useState } from "react";
import { useAuth } from "../context/AuthContext";
import { useNavigate } from "react-router-dom";
import PageHeader from "../components/PageHeader";
import WeightProgress from "../components/WeightProgress";
import { Loading } from "../components/Status";
import ConfirmDialog from "../components/ConfirmDialog";
import { isProfileIncomplete, formatHeight } from "../lib/profile";
import { useProfileStats } from "../lib/useProfileStats";
import SettingsButton from "../components/SettingsButton";
import { nextReportInfo } from "../lib/reports";
import { usePwaInstall } from "../lib/pwaInstall";

export default function ProfilePage() {
  const { user, loading, logout } = useAuth();
  const navigate = useNavigate();
  const [confirmingLogout, setConfirmingLogout] = useState(false);
  const { stats, latestReport, reportSettings, statsLoading } = useProfileStats();
  const nextReport = nextReportInfo(reportSettings);
  const overCalories = stats.calorieTarget > 0 && stats.caloriesToday > stats.calorieTarget;

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
    <div className="page">
      <PageHeader
        title="Profile"
        action={<SettingsButton to="/profile/edit" label="Edit profile" />}
      />

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

            <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 8 }}>
              <StatBox label="This week" value={stats.workoutsThisWeek} unit="workouts" accent="bamboo" onClick={() => navigate("/workouts")} />
              <StatBox label="Log Streak" value={stats.streak} unit="days" accent="turmeric" />
              <StatBox label="Workout streak" value={stats.workoutStreak} unit="days" accent="ube" />
            </div>

{stats.calorieTarget > 0 && (
  <div style={{ borderTop: "1px solid var(--border-soft)", paddingTop: 14, display: "flex", flexDirection: "column", gap: 8 }}>
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
      <span className="eyebrow">Today's calories</span>
      <span className="stat" style={{ fontSize: 12, color: overCalories ? "var(--chili)" : "var(--text-dim)" }}>
        {stats.caloriesToday} / {stats.calorieTarget} kcal
      </span>
    </div>
    <div className="progress-track">
      <div
        className="progress-fill"
        style={{
          width: `${Math.min(100, (stats.caloriesToday / stats.calorieTarget) * 100)}%`,
          "--accent-color": overCalories ? "var(--chili)" : "var(--bamboo)",
        }}
      />
    </div>
  </div>
)}

          <div style={{ display: "flex", flexDirection: "column", gap: 8, borderTop: "1px solid var(--border-soft)", paddingTop: 14 }}>
            <LinkRow
              label="Latest report"
              value={latestReport ? `Report #${latestReport.report_number}` : "None yet"}
              onClick={() => navigate(latestReport ? `/progress/${latestReport.id}` : "/progress")}
            />
            {nextReport && (
              <LinkRow label="Next report" value={nextReport.text} onClick={() => navigate("/progress/settings")} />
            )}
            <InstallRow />
          </div>
          </div>
        </div>

        <div className="profile-col-right">
          <WeightProgress />
        </div>
      </div>

      <div className="page-actions">
        <button
          className="btn btn-secondary btn-block"
          style={{ color: "var(--chili)" }}
          onClick={() => setConfirmingLogout(true)}
        >
          Log Out
        </button>
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

function LinkRow({ label, value, onClick }) {
  return (
    <div
      onClick={onClick}
      style={{ display: "flex", justifyContent: "space-between", fontSize: 14, cursor: "pointer", padding: "6px 0" }}
    >
      <span style={{ color: "var(--text-dim)" }}>{label}</span>
      <span style={{ fontWeight: 500 }}>{value} ›</span>
    </div>
  );
}

function InstallRow() {
  const { installed, canPrompt, showIosHelp, install } = usePwaInstall();
  const [helpOpen, setHelpOpen] = useState(false);

  if (installed || (!canPrompt && !showIosHelp)) return null;

  return (
    <div>
      <LinkRow
        label="Install app"
        value={canPrompt ? "Add to your device" : "How to install"}
        onClick={canPrompt ? install : () => setHelpOpen((o) => !o)}
      />
      {helpOpen && (
        <p style={{ fontSize: 12, color: "var(--text-faint)", padding: "0 0 6px" }}>
          Tap the Share button in Safari, then choose "Add to Home Screen".
        </p>
      )}
    </div>
  );
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