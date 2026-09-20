import { useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { updateProfile, logWeight } from "../api/accounts";
import { ErrorBanner, extractErrorMessage } from "./Status";
import WeightField from "./WeightField";
import { formatWeight } from "../lib/profile";
import { useToast } from "../context/ToastContext";

const todayStr = () => new Date().toISOString().split("T")[0];

// Embedded on the Profile page -- deliberately minimal (a glance +
// two big actions), not the full chart/history experience. That lives
// at /profile/weight (see pages/WeightLog.jsx) so a first-time user
// isn't faced with a graph and a log table before they've even logged
// anything. Doesn't need the weight-log list at all -- current weight
// comes straight from the already-derived profile.current_weight_kg.
export default function WeightProgress() {
  const { user, refreshUser } = useAuth();
  const showToast = useToast();
  const [mode, setMode] = useState(null); // null | "log" | "goal"

  const currentWeight = user?.profile?.current_weight_kg ?? null;
  const currentGoal = user?.profile?.goal_weight_kg ?? null;
  const unitSystem = user?.profile?.unit_system || "metric";

  return (
    <div className="card weight-progress-card" style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <h3>Weight</h3>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
        <StatTile label="Current" value={currentWeight != null ? formatWeight(currentWeight, unitSystem) : "Not logged"} />
        <StatTile label="Goal" value={currentGoal != null ? formatWeight(currentGoal, unitSystem) : "Not set"} accent="turmeric" />
      </div>

      {mode === null && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
          <button className="btn btn-primary" style={{ padding: "10px 14px", fontSize: 13 }} onClick={() => setMode("log")}>
            Log Weight
          </button>
          <button className="btn btn-secondary" style={{ padding: "10px 14px", fontSize: 13 }} onClick={() => setMode("goal")}>
            {currentGoal != null ? "Change Goal" : "Set Goal"}
          </button>
        </div>
      )}

      {mode === "log" && (
        <QuickLogForm
          unitSystem={unitSystem}
          onDone={async () => { await refreshUser(); showToast("Weight logged", "success"); setMode(null); }}
          onCancel={() => setMode(null)}
        />
      )}
      {mode === "goal" && (
        <QuickGoalForm
          currentGoal={currentGoal}
          unitSystem={unitSystem}
          onDone={async () => { await refreshUser(); showToast("Goal weight updated", "success"); setMode(null); }}
          onCancel={() => setMode(null)}
        />
      )}

      <Link to="/profile/weight" style={{ fontSize: 13, color: "var(--chili)", fontWeight: 600, textAlign: "center" }}>
        View history &amp; trends &rarr;
      </Link>
    </div>
  );
}

function StatTile({ label, value, accent }) {
  return (
    <div style={{ textAlign: "center", padding: "10px 4px", background: "var(--bg-raised)", borderRadius: "var(--radius-sm)" }}>
      <div style={{ fontSize: 16, fontWeight: 700, color: accent ? `var(--${accent})` : "var(--text)" }}>{value}</div>
      <div className="eyebrow" style={{ marginTop: 4 }}>{label}</div>
    </div>
  );
}

// No date field on purpose -- this is the quick path (defaults to
// today). Logging for a past date is a /profile/weight thing.
function QuickLogForm({ unitSystem, onDone, onCancel }) {
  const [weightKg, setWeightKg] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function handleSave() {
    if (weightKg === "") return;
    setSaving(true);
    setError("");
    try {
      await logWeight({ weightKg: Number(weightKg), loggedAt: todayStr() });
      await onDone();
    } catch (err) {
      setError(extractErrorMessage(err, "Couldn't log that weight."));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div>
      <WeightField
        autoFocus
        label="Today's weight"
        kg={weightKg}
        onChange={setWeightKg}
        placeholder="e.g. 78.5"
        defaultUnit={unitSystem === "imperial" ? "lbs" : "kg"}
        allowToggle={false}
      />
      <ErrorBanner message={error} />
      <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
        <button className="btn btn-primary" style={{ padding: "8px 14px", fontSize: 13, flex: 1 }} onClick={handleSave} disabled={saving}>
          {saving ? "Saving..." : "Save"}
        </button>
        <button className="btn btn-secondary" style={{ padding: "8px 14px", fontSize: 13, flex: 1 }} onClick={onCancel} disabled={saving}>
          Cancel
        </button>
      </div>
    </div>
  );
}

function QuickGoalForm({ currentGoal, unitSystem, onDone, onCancel }) {
  const [goalWeightKg, setGoalWeightKg] = useState(currentGoal ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function handleSave() {
    setSaving(true);
    setError("");
    try {
      await updateProfile({ goal_weight_kg: goalWeightKg !== "" ? Number(goalWeightKg) : null });
      await onDone();
    } catch (err) {
      setError(extractErrorMessage(err, "Couldn't update goal weight."));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div>
      <WeightField
        autoFocus
        label="Goal weight"
        kg={goalWeightKg}
        onChange={setGoalWeightKg}
        placeholder="e.g. 75"
        defaultUnit={unitSystem === "imperial" ? "lbs" : "kg"}
        allowToggle={false}
      />
      <ErrorBanner message={error} />
      <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
        <button className="btn btn-primary" style={{ padding: "8px 14px", fontSize: 13, flex: 1 }} onClick={handleSave} disabled={saving}>
          {saving ? "Saving..." : "Save"}
        </button>
        <button className="btn btn-secondary" style={{ padding: "8px 14px", fontSize: 13, flex: 1 }} onClick={onCancel} disabled={saving}>
          Cancel
        </button>
      </div>
    </div>
  );
}
