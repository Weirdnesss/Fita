import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { logWeight, listWeightLogs, deleteWeightLog, updateProfile } from "../api/accounts";
import { Loading, ErrorBanner, extractErrorMessage } from "./Status";
import WeightField from "./WeightField";
import { formatWeight, formatWeightDelta } from "../lib/profile";
import ConfirmDialog from "./ConfirmDialog";
import { useToast } from "../context/ToastContext";

const todayStr = () => new Date().toISOString().split("T")[0];

// Embedded directly on the Profile page, under Details -- goal-weight
// editing, the trend graph, logging a new entry, and history all live
// here as one section rather than a separate page/route.
export default function WeightProgress() {
  const { user, refreshUser } = useAuth();
  const navigate = useNavigate();
  const showToast = useToast();
  const [logs, setLogs] = useState(null);
  const [weightKg, setWeightKg] = useState("");
  const [loggedAt, setLoggedAt] = useState(todayStr());
  const [saving, setSaving] = useState(false);
  const [deletingId, setDeletingId] = useState(null);
  const [error, setError] = useState("");
  const [pendingDelete, setPendingDelete] = useState(null); // { id, weightKg } | null

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
      showToast("Weight logged", "success");
    } catch (err) {
      setError(extractErrorMessage(err, "Couldn't log that weight."));
    } finally {
      setSaving(false);
    }
  }

  async function confirmDelete() {
    const { id, weightKg } = pendingDelete;
    setPendingDelete(null);
    setDeletingId(id);
    setError("");
    try {
      await deleteWeightLog(id);
      await load();
      await refreshUser();
      showToast(`Removed ${formatWeight(weightKg, unitSystem)} entry`, "success");
    } catch (err) {
      showToast(extractErrorMessage(err, "Couldn't delete that entry."), "error");
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
      showToast("Goal weight updated", "success");
      setEditingGoal(false);
    } catch (err) {
      setError(extractErrorMessage(err, "Couldn't update goal weight."));
    } finally {
      setSavingGoal(false);
    }
  }

  const currentGoal = user?.profile?.goal_weight_kg ?? null;
  const unitSystem = user?.profile?.unit_system || "metric";

  return (
    <div className="card weight-progress-card" style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <h3>Weight Progress</h3>

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <p className="eyebrow">Goal weight</p>
          {!editingGoal && (
            <p style={{ fontSize: 20, fontWeight: 700 }}>
              {currentGoal != null ? formatWeight(currentGoal, unitSystem) : "Not set"}
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
        <div style={{ marginTop: -8 }}>
          <WeightField
            autoFocus
            label="Goal weight"
            kg={goalWeightKg}
            onChange={setGoalWeightKg}
            placeholder="e.g. 75"
            defaultUnit={unitSystem === "imperial" ? "lbs" : "kg"}
            allowToggle={false}
          />
          <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
            <button className="btn btn-primary" style={{ padding: "8px 14px", fontSize: 13, flex: 1 }} onClick={handleSaveGoal} disabled={savingGoal}>
              {savingGoal ? "Saving..." : "Save"}
            </button>
            <button className="btn btn-secondary" style={{ padding: "8px 14px", fontSize: 13, flex: 1 }} onClick={() => setEditingGoal(false)} disabled={savingGoal}>
              Cancel
            </button>
          </div>
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
        {logs !== null && logs.length >= 2 && (
          <WeightChart logs={logs} goalWeightKg={currentGoal} primaryGoal={user?.profile?.primary_goal} unitSystem={unitSystem} />
        )}
      </div>

      <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
          <div>
            <WeightField
              required
              label="Weight"
              kg={weightKg}
              onChange={setWeightKg}
              placeholder="e.g. 78.5"
              defaultUnit={unitSystem === "imperial" ? "lbs" : "kg"}
              allowToggle={false}
            />
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
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
          <p className="eyebrow" style={{ margin: 0 }}>
            Recent entries
          </p>

          <button
            className="btn-ghost"
            style={{
              background: "none",
              border: "none",
              padding: 0,
              fontSize: 13,
              color: "var(--text-dim)",
            }}
            onClick={() => navigate("weight")}
          >
            View Weight Log →
          </button>
        </div>

        {logs !== null && logs.length === 0 && (
          <p style={{ fontSize: 13, color: "var(--text-faint)" }}>
            No entries yet — log your first weight above.
          </p>
        )}

        {logs?.slice(0, 5).map((entry) => (
          <div
            key={entry.id}
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              padding: "8px 0",
              borderBottom: "1px solid var(--border)",
            }}
          >
            <div>
              <p style={{ fontWeight: 600, fontSize: 14 }}>
                {formatWeight(entry.weight_kg, unitSystem)}
              </p>
              <p style={{ fontSize: 12, color: "var(--text-faint)" }}>
                {entry.logged_at}
              </p>
            </div>

            <button
              className="btn-ghost"
              style={{
                background: "none",
                border: "none",
                color: "var(--chili)",
                fontSize: 12,
                padding: 6,
              }}
              onClick={() =>
                setPendingDelete({
                  id: entry.id,
                  weightKg: entry.weight_kg,
                })
              }
              disabled={deletingId === entry.id}
            >
              {deletingId === entry.id ? "Removing..." : "Remove"}
            </button>
          </div>
        ))}
      </div>
        <ConfirmDialog
        open={pendingDelete !== null}
        title="Remove entry"
        message={pendingDelete ? `Remove the ${formatWeight(pendingDelete.weightKg, unitSystem)} entry? This can't be undone.` : ""}
        confirmLabel="Remove"
        onConfirm={confirmDelete}
        onCancel={() => setPendingDelete(null)}
      />
    </div>
  );
}

// Lightweight hand-rolled SVG line chart -- no charting library is
// installed in this project, and adding one for a single chart felt
// like overkill. Plots logged_at (x) against weight_kg (y), with an
// optional dashed reference line for goal weight. `logs` comes in
// most-recent-first (the API's default ordering), so it's reversed
// here to plot left-to-right chronologically.
// Which direction of weight change counts as "good" depends on the
// user's actual goal -- losing weight is progress for lose_weight, but
// it's the opposite of progress for gain_weight/gain_muscle. Mirrors
// accounts.models.PrimaryGoal on the backend. maintain_weight and
// build_strength aren't about weight direction at all, so neither
// direction is colored as good/bad for those (or if the goal isn't set).
function goalWeightDirection(primaryGoal) {
  if (primaryGoal === "lose_weight") return "down";
  if (primaryGoal === "gain_weight" || primaryGoal === "gain_muscle") return "up";
  return null;
}

function WeightChart({ logs, goalWeightKg, primaryGoal, unitSystem = "metric" }) {
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
  const changeDelta = formatWeightDelta(change, unitSystem);
  const direction = goalWeightDirection(primaryGoal);
  const isGoodChange = change === 0 ? null : direction === "down" ? change < 0 : direction === "up" ? change > 0 : null;
  const changeColor = isGoodChange === null ? "var(--text)" : isGoodChange ? "var(--bamboo)" : "var(--chili)";

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
        <span>Latest: <strong style={{ color: "var(--text)" }}>{formatWeight(latest.weight_kg, unitSystem)}</strong></span>
        <span>
          Change: <strong style={{ color: changeColor }}>
            {changeDelta.value > 0 ? "+" : ""}{changeDelta.value} {changeDelta.unit}
          </strong>
        </span>
        {goalWeightKg != null && <span>Goal: <strong style={{ color: "var(--turmeric)" }}>{formatWeight(goalWeightKg, unitSystem)}</strong></span>}
      </div>
    </div>
  );
}