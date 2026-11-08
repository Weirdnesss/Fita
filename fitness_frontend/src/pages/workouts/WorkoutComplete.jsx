import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { formatElapsed } from "../../lib/activeWorkout";
import StickyBar from "../../components/StickyBar";
import Pinned from "../../components/Pinned";

function Stat({ label, value }) {
  return (
    <div className="card" style={{ flex: 1, textAlign: "center", padding: "12px 6px" }}>
      <p className="stat" style={{ fontSize: 22, fontWeight: 700 }}>{value}</p>
      <p style={{ fontSize: 11, color: "var(--text-faint)", textTransform: "uppercase", letterSpacing: 0.5 }}>{label}</p>
    </div>
  );
}

/** Shown right after Finish. The numbers arrive through router state; a reload just goes back. */
export default function WorkoutComplete() {
  const navigate = useNavigate();
  const summary = useLocation().state?.summary;
  if (!summary) return <Navigate to="/workouts" replace />;

  return (
    <div className="page">
      <StickyBar>
      <div style={{ textAlign: "center", padding: "16px 0 4px" }}>
        <div
          aria-hidden="true"
          style={{
            width: 64, height: 64, borderRadius: "50%", margin: "0 auto 12px",
            background: "var(--bamboo)", color: "#fff", display: "flex", alignItems: "center", justifyContent: "center",
          }}
        >
          <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
            <path d="M5 12.5l4.5 4.5L19 7.5" />
          </svg>
        </div>
        <h1>Workout complete</h1>
        <p style={{ color: "var(--text-dim)" }}>{summary.title}</p>
      </div>

      <div style={{ display: "flex", gap: 8 }}>
        <Stat label="Time" value={formatElapsed(summary.durationSeconds)} />
        <Stat label="Sets" value={summary.totalSets} />
        {summary.volumeKg > 0 && <Stat label="Volume (kg)" value={summary.volumeKg.toLocaleString()} />}
      </div>
      </StickyBar>
      <div className="card">
        <p className="eyebrow" style={{ marginBottom: 8 }}>What you did</p>
        {summary.exercises.map((ex, i) => (
          <div
            key={i}
            style={{ display: "flex", justifyContent: "space-between", gap: 12, padding: "8px 0", borderTop: i ? "1px solid var(--border)" : "none" }}
          >
            <span style={{ fontWeight: 600, minWidth: 0 }}>{ex.name}</span>
            <span style={{ color: "var(--text-dim)", fontSize: 13, textAlign: "right", flexShrink: 0 }}>{ex.detail}</span>
          </div>
        ))}
      </div>
      <Pinned>
      <button className="btn btn-primary" style={{ width: "100%" }} onClick={() => navigate("/workouts", { replace: true })}>
        Done
      </button>
      {summary.historyId && (
        <button className="btn-ghost" style={{ width: "100%", padding: 10 }} onClick={() => navigate(`/workouts/history/${summary.historyId}`)}>
          View in history
        </button>
      )}
      </Pinned>
    </div>
  );
}
