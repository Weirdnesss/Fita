import { useState } from "react";
import { useAuth } from "../../context/AuthContext";
import { logWeight } from "../../api/accounts";
import { ErrorBanner, extractErrorMessage } from "../Status";
import WeightField from "../WeightField";
import { useToast } from "../../context/ToastContext";

const todayStr = () => new Date().toISOString().split("T")[0];

// Matches the backend's WeightLogSerializer.validate_logged_at: the
// later of (today - 7 days) or account creation. Backdating further
// back than that is more likely a guess than an actual memory, and
// there's nothing meaningful to backdate to before the account existed
// anyway. This is a UI convenience (disables invalid dates up front)
// -- the backend enforces the same rule regardless, so bypassing this
// via devtools still gets rejected server-side.
function earliestLoggableDate(user) {
  const sevenDaysAgo = new Date();
  sevenDaysAgo.setDate(sevenDaysAgo.getDate() - 7);
  const signupDate = user?.date_joined ? new Date(user.date_joined) : null;
  const floor = signupDate && signupDate > sevenDaysAgo ? signupDate : sevenDaysAgo;
  return floor.toISOString().split("T")[0];
}

export default function LogWeightForm({ onLogged }) {
  const { user, refreshUser } = useAuth();
  const showToast = useToast();
  const [weightKg, setWeightKg] = useState("");
  const [loggedAt, setLoggedAt] = useState(todayStr());
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const unitSystem = user?.profile?.unit_system || "metric";
  const minDate = earliestLoggableDate(user);

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
          <input type="date" min={minDate} max={todayStr()} value={loggedAt} onChange={(e) => setLoggedAt(e.target.value)} />
        </div>
      </div>
      <p style={{ fontSize: 12, color: "var(--text-faint)" }}>
        You can log up to 7 days back (or since you joined, if that's sooner). Logging again for a date you've
        already logged updates that entry instead of adding a duplicate.
      </p>
      <ErrorBanner message={error} />
      <button className="btn btn-primary" disabled={saving}>{saving ? "Saving..." : "Log Weight"}</button>
    </form>
  );
}
