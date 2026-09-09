import { useEffect, useState } from "react";
import { useAuth } from "../context/AuthContext";
import { logWeight, listWeightLogs, deleteWeightLog, updateProfile } from "../api/accounts";
import { Loading, ErrorBanner, extractErrorMessage } from "./Status";

const todayStr = () => new Date().toISOString().split("T")[0];

// Embedded directly on the Profile page, under Details -- goal-weight
// editing, the trend graph, logging a new entry, and history all live
// here as one section rather than a separate page/route.
export default function WeightProgress() {
  const { user, refreshUser } = useAuth();
  const [logs, setLogs] = useState(null);
  const [weightKg, setWeightKg] = useState("");
  const [loggedAt, setLoggedAt] = useState(todayStr());
  const [saving, setSaving] = useState(false);
  const [deletingId, setDeletingId] = useState(null);
  const [error, setError] = useState("");
  const [showHistory, setShowHistory] = useState(false);

  const [editingGoal, setEditingGoal] = useState(false);
  const [goalWeightKg, setGoalWeightKg] = useState(user?.profile?.goal_weight_kg ?? "");
  const [savingGoal, setSavingGoal] = useState(false);

  async function load() {
    try {
      setLogs(await listWeightLogs());
    } catch (err) {
      setError(extractErrorMessage(err, "Couldn't load weight history."));
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function handleSubmit(e) {
    e.preventDefault();
    if (weightKg === "") return;
    setError("");
    setSaving(true);
    try {
      await logWeight({ weightKg: Number(weightKg), loggedAt });
      setWeightKg("");
      setLoggedAt(todayStr());
      await load();
      // So the rest of the Profile page (and anywhere else user.profile
      // is read) shows the new current_weight_kg immediately.
      await refreshUser();
    } catch (err) {
      setError(extractErrorMessage(err, "Couldn't log that weight."));
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(id) {
    setDeletingId(id);
    setError("");
    try {
      await deleteWeightLog(id);
      await load();
      await refreshUser();
    } catch (err) {
      setError(extractErrorMessage(err, "Couldn't delete that entry."));
    } finally {
      setDeletingId(null);
    }
  }

  async function handleSaveGoal() {
    setSavingGoal(true);
    setError("");
    try {
      await updateProfile({ goal_weight_kg: goalWeightKg !== "" ? Number(goalWeightKg) : null });
      await refreshUser();
      setEditingGoal(false);
    } catch (err) {
      setError(extractErrorMessage(err, "Couldn't update goal weight."));
    } finally {
      setSavingGoal(false);
    }
  }

  const currentGoal = user?.profile?.goal_weight_kg ?? null;

  return (
    <div className="card" style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <h3>Weight Progress</h3>

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <p className="eyebrow">Goal weight</p>
          {!editingGoal && (
            <p style={{ fontSize: 20, fontWeight: 700 }}>
              {currentGoal != null ? `${currentGoal} kg` : "Not set"}
            </p>
          )}
        </div>
        {!editingGoal && (
          <button
            className="btn-ghost"
            style={{ background: "none", border: "1px solid var(--border)", fontSize: 12, padding: "6px 12px", borderRadius: "var(--radius-sm)" }}
            onClick={() => { setGoalWeightKg(currentGoal ?? ""); setEditingGoal(true); }}
          >
            {currentGoal != null ? "Change" : "Set goal"}
          </button>
        )}
      </div>
      {editingGoal && (
        <div style={{ display: "flex", gap: 8, marginTop: -8 }}>
          <input
            type="number" step="0.1" autoFocus placeholder="e.g. 75"
            value={goalWeightKg} onChange={(e) => setGoalWeightKg(e.target.value)}
            style={{ flex: 1 }}
          />
          <button className="btn btn-primary" style={{ padding: "8px 14px", fontSize: 13 }} onClick={handleSaveGoal} disabled={savingGoal}>
            {savingGoal ? "Saving..." : "Save"}
          </button>
          <button className="btn btn-secondary" style={{ padding: "8px 14px", fontSize: 13 }} onClick={() => setEditingGoal(false)} disabled={savingGoal}>
            Cancel
          </button>
        </div>
      )}

      <div>
        <p className="eyebrow" style={{ marginBottom: 8 }}>Trend</p>
        {logs === null && <Loading />}
        {logs !== null && logs.length < 2 && (
          <p style={{ fontSize: 13, color: "var(--text-faint)" }}>
            Log at least 2 entries to see a trend graph.
          </p>
        )}
        {logs !== null && logs.length >= 2 && <WeightChart logs={logs} goalWeightKg={currentGoal} />}
      </div>

      <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
          <div>
            <label>Weight (kg)</label>
            <input type="number" step="0.1" required value={weightKg} onChange={(e) => setWeightKg(e.target.value)} placeholder="e.g. 78.5" />
          </div>
          <div>
            <label>Date</label>
            <input type="date" max={todayStr()} value={loggedAt} onChange={(e) => setLoggedAt(e.target.value)} />
          </div>
        </div>
        <p style={{ fontSize: 12, color: "var(--text-faint)" }}>
          Logging again for a date you've already logged updates that entry instead of adding a duplicate.
        </p>
        <ErrorBanner message={error} />
        <button className="btn btn-primary" disabled={saving}>{saving ? "Saving..." : "Log Weight"}</button>
      </form>

      <div>
        <button
          className="btn-ghost"
          style={{ background: "none", border: "none", padding: 0, fontSize: 13, color: "var(--text-dim)" }}
          onClick={() => setShowHistory((s) => !s)}
        >
          {showHistory ? "Hide history" : `Show history${logs ? ` (${logs.length})` : ""}`}
        </button>
        {showHistory && (
          <div style={{ marginTop: 10 }}>
            {logs !== null && logs.length === 0 && (
              <p style={{ fontSize: 13, color: "var(--text-faint)" }}>No entries yet -- log your first weight above.</p>
            )}
            {logs?.map((entry) => (
              <div key={entry.id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "8px 0", borderBottom: "1px solid var(--border)" }}>
                <div>
                  <p style={{ fontWeight: 600, fontSize: 14 }}>{entry.weight_kg} kg</p>
                  <p style={{ fontSize: 12, color: "var(--text-faint)" }}>{entry.logged_at}</p>
                </div>
                <button
                  className="btn-ghost"
                  style={{ background: "none", border: "none", color: "var(--chili)", fontSize: 12, padding: 6 }}
                  onClick={() => handleDelete(entry.id)}
                  disabled={deletingId === entry.id}
                >
                  {deletingId === entry.id ? "Removing..." : "Remove"}
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// Lightweight hand-rolled SVG line chart -- no charting library is
// installed in this project, and adding one for a single chart felt
// like overkill. Plots logged_at (x) against weight_kg (y), with an
// optional dashed reference line for goal weight. `logs` comes in
// most-recent-first (the API's default ordering), so it's reversed
// here to plot left-to-right chronologically.
function WeightChart({ logs, goalWeightKg }) {
  const width = 320;
  const height = 150;
  const padding = { top: 14, right: 14, bottom: 20, left: 14 };

  const chronological = [...logs].reverse();
  const weights = chronological.map((e) => e.weight_kg);
  const times = chronological.map((e) => new Date(e.logged_at).getTime());

  const dataMin = Math.min(...weights);
  const dataMax = Math.max(...weights);
  let scaleMin = goalWeightKg != null ? Math.min(dataMin, goalWeightKg) : dataMin;
  let scaleMax = goalWeightKg != null ? Math.max(dataMax, goalWeightKg) : dataMax;
  const span = scaleMax - scaleMin || 1;
  scaleMin -= span * 0.12;
  scaleMax += span * 0.12;

  const minTime = Math.min(...times);
  const maxTime = Math.max(...times);
  const timeSpan = maxTime - minTime || 1;

  const plotWidth = width - padding.left - padding.right;
  const plotHeight = height - padding.top - padding.bottom;

  const xFor = (t) => padding.left + ((t - minTime) / timeSpan) * plotWidth;
  const yFor = (w) => padding.top + plotHeight - ((w - scaleMin) / (scaleMax - scaleMin)) * plotHeight;

  const points = chronological.map((e) => `${xFor(new Date(e.logged_at).getTime())},${yFor(e.weight_kg)}`).join(" ");
  const latest = chronological[chronological.length - 1];
  const first = chronological[0];
  const change = Math.round((latest.weight_kg - first.weight_kg) * 10) / 10;

  return (
    <div>
      <svg viewBox={`0 0 ${width} ${height}`} style={{ width: "100%", height: "auto", display: "block" }}>
        {goalWeightKg != null && (
          <line
            x1={padding.left} x2={width - padding.right}
            y1={yFor(goalWeightKg)} y2={yFor(goalWeightKg)}
            stroke="var(--turmeric)" strokeWidth="1.5" strokeDasharray="4 3"
          />
        )}
        <polyline points={points} fill="none" stroke="var(--bamboo)" strokeWidth="2.5" strokeLinejoin="round" strokeLinecap="round" />
        {chronological.map((e) => (
          <circle key={e.id} cx={xFor(new Date(e.logged_at).getTime())} cy={yFor(e.weight_kg)} r="3" fill="var(--bamboo)" />
        ))}
        <text x={padding.left} y={height - 4} fontSize="9" fill="var(--text-faint)">{first.logged_at}</text>
        <text x={width - padding.right} y={height - 4} fontSize="9" fill="var(--text-faint)" textAnchor="end">{latest.logged_at}</text>
      </svg>
      <div style={{ display: "flex", justifyContent: "space-between", marginTop: 8, fontSize: 12, color: "var(--text-faint)" }}>
        <span>Latest: <strong style={{ color: "var(--text)" }}>{latest.weight_kg} kg</strong></span>
        <span>
          Change: <strong style={{ color: change < 0 ? "var(--bamboo)" : change > 0 ? "var(--chili)" : "var(--text)" }}>
            {change > 0 ? "+" : ""}{change} kg
          </strong>
        </span>
        {goalWeightKg != null && <span>Goal: <strong style={{ color: "var(--turmeric)" }}>{goalWeightKg} kg</strong></span>}
      </div>
    </div>
  );
}