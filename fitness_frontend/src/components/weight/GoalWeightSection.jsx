import { useState } from "react";
import { useAuth } from "../../context/AuthContext";
import { updateProfile } from "../../api/accounts";
import { ErrorBanner, extractErrorMessage } from "../Status";
import WeightField from "../WeightField";
import { formatWeight } from "../../lib/profile";
import { useToast } from "../../context/ToastContext";

export default function GoalWeightSection() {
  const { user, refreshUser } = useAuth();
  const showToast = useToast();
  const [editing, setEditing] = useState(false);
  const [goalWeightKg, setGoalWeightKg] = useState(user?.profile?.goal_weight_kg ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const currentGoal = user?.profile?.goal_weight_kg ?? null;
  const unitSystem = user?.profile?.unit_system || "metric";

  async function handleSave() {
    setSaving(true);
    setError("");
    try {
      await updateProfile({ goal_weight_kg: goalWeightKg !== "" ? Number(goalWeightKg) : null });
      await refreshUser();
      showToast("Goal weight updated", "success");
      setEditing(false);
    } catch (err) {
      setError(extractErrorMessage(err, "Couldn't update goal weight."));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <p className="eyebrow">Goal weight</p>
          {!editing && (
            <p style={{ fontSize: 20, fontWeight: 700 }}>
              {currentGoal != null ? formatWeight(currentGoal, unitSystem) : "Not set"}
            </p>
          )}
        </div>
        {!editing && (
          <button
            className="btn-ghost"
            style={{ background: "none", border: "1px solid var(--border)", fontSize: 12, padding: "6px 12px", borderRadius: "var(--radius-sm)" }}
            onClick={() => { setGoalWeightKg(currentGoal ?? ""); setEditing(true); }}
          >
            {currentGoal != null ? "Change" : "Set goal"}
          </button>
        )}
      </div>
      {editing && (
        <div style={{ marginTop: 10 }}>
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
            <button className="btn btn-secondary" style={{ padding: "8px 14px", fontSize: 13, flex: 1 }} onClick={() => setEditing(false)} disabled={saving}>
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
