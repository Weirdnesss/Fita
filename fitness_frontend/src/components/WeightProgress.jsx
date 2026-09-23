import { useEffect, useState } from "react";
import { useAuth } from "../context/AuthContext";
import { updateProfile, logWeight, listWeightLogs } from "../api/accounts";
import { ErrorBanner, Loading, extractErrorMessage } from "./Status";
import WeightField from "./WeightField";
import WeightChart from "./weight/WeightChart";
import WeightHistoryList from "./weight/WeightHistoryList";
import { formatWeight } from "../lib/profile";
import { useToast } from "../context/ToastContext";
import LogWeightForm from "./weight/LogWeightForm";

const todayStr = () => new Date().toISOString().split("T")[0];

// Embedded on the Profile page. Log/goal actions stay up top (the
// quick path -- defaults to today, no date field), with Trend and
// History as tabs below. Previously the full chart/history lived at
// /profile/weight (pages/WeightLog.jsx) as a separate destination;
// merged in here so there's exactly one place weight lives, not two
// partially-overlapping ones. /profile/weight and WeightLog.jsx
// should be removed once this ships (see App.jsx routes).
export default function WeightProgress() {
  const { user, refreshUser } = useAuth();
  const showToast = useToast();
  const [mode, setMode] = useState(null); // null | "log" | "goal"
  const [tab, setTab] = useState("trend"); // "trend" | "history"
  const [logs, setLogs] = useState(null);
  const [error, setError] = useState("");

  const currentWeight = user?.profile?.current_weight_kg ?? null;
  const currentGoal = user?.profile?.goal_weight_kg ?? null;
  const unitSystem = user?.profile?.unit_system || "metric";
  const primaryGoal = user?.profile?.primary_goal ?? null;
  const bmi = user?.profile?.bmi ?? null;
  

  useEffect(() => {
    load();
  }, []);

  async function load() {
    try {
      const data = await listWeightLogs();
      setLogs(data);
    } catch (err) {
      setError(extractErrorMessage(err, "Couldn't load weight history."));
    }
  }

  return (
    <div className="card weight-progress-card" style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <h3>Weight</h3>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 10 }}>
        <StatTile label="Current" value={currentWeight != null ? formatWeight(currentWeight, unitSystem) : "Not logged"} accent="bamboo" />
        <StatTile label="Goal" value={currentGoal != null ? formatWeight(currentGoal, unitSystem) : "Not set"} accent="turmeric" />
        <StatTile label="BMI" value={bmi ?? "--"} accent="ube" />
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
        <LogWeightForm
          onLogged={async () => {
            await load();
            setMode(null);
          }}
          onCancel={() => setMode(null)}
        />
      )}

      {mode === "goal" && (
        <QuickGoalForm
          currentGoal={currentGoal}
          unitSystem={unitSystem}
          onDone={async () => {
            await refreshUser();
            showToast("Goal weight updated", "success");
            setMode(null);
          }}
          onCancel={() => setMode(null)}
        />
      )}

      <div style={{ borderTop: "1px solid var(--border-soft)", paddingTop: 14 }}>
        <div className="tab-bar" style={{ marginBottom: 14 }}>
          <button className={`tab-btn${tab === "trend" ? " active" : ""}`} onClick={() => setTab("trend")}>
            Trend
          </button>
          <button className={`tab-btn${tab === "history" ? " active" : ""}`} onClick={() => setTab("history")}>
            History
          </button>
        </div>

        <ErrorBanner message={error} />

        {logs === null && !error && <Loading />}

        {logs !== null && logs.length === 0 && (
          <p style={{ fontSize: 13, color: "var(--text-faint)" }}>No entries yet -- log your first weight above.</p>
        )}

        {logs?.length > 0 && tab === "trend" && (
          <WeightChart logs={logs} goalWeightKg={currentGoal} primaryGoal={primaryGoal} unitSystem={unitSystem} />
        )}

        {logs?.length > 0 && tab === "history" && (
          <WeightHistoryList
            logs={logs}
            unitSystem={unitSystem}
            onDeleted={load}
          />
        )}
      </div>
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