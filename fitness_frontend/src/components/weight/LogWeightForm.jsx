import { useState } from "react";
import { useAuth } from "../../context/AuthContext";
import { logWeight } from "../../api/accounts";
import { ErrorBanner, extractErrorMessage } from "../Status";
import WeightField from "../WeightField";
import { useToast } from "../../context/ToastContext";

const todayStr = () => new Date().toISOString().split("T")[0];

export default function LogWeightForm({ onLogged }) {
  const { user, refreshUser } = useAuth();
  const showToast = useToast();
  const [weightKg, setWeightKg] = useState("");
  const [loggedAt, setLoggedAt] = useState(todayStr());
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const unitSystem = user?.profile?.unit_system || "metric";

  async function handleSubmit(e) {
    e.preventDefault();
    if (weightKg === "") return;
    setError("");
    setSaving(true);
    try {
      await logWeight({ weightKg: Number(weightKg), loggedAt });
      setWeightKg("");
      setLoggedAt(todayStr());
      // So the rest of the app (Profile, Edit Profile, anywhere else
      // user.profile is read) shows the new current_weight_kg immediately.
      await refreshUser();
      showToast("Weight logged", "success");
      onLogged?.();
    } catch (err) {
      setError(extractErrorMessage(err, "Couldn't log that weight."));
    } finally {
      setSaving(false);
    }
  }

  return (
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
  );
}
