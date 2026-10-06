import { useState } from "react";
import { useAuth } from "../../context/AuthContext";
import { logWeight } from "../../api/accounts";
import { ErrorBanner, extractErrorMessage } from "../Status";
import WeightField from "../WeightField";
import DatePicker from "../DatePicker";
import { useToast } from "../../context/ToastContext";

// Local calendar date as YYYY-MM-DD. Not toISOString() -- that's UTC,
// which reads as yesterday in the Philippines before 8 AM local.
function toDateStr(date) {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

const todayStr = () => toDateStr(new Date());

// Matches the backend's WeightLogSerializer.validate_logged_at: the
// later of (today - 7 days) or account creation. This is a UI
// convenience (DatePicker disables invalid dates up front) -- the
// backend enforces the same rule regardless.
function earliestLoggableDate(user) {
  const sevenDaysAgo = new Date();
  sevenDaysAgo.setDate(sevenDaysAgo.getDate() - 7);
  const signupDate = user?.date_joined ? new Date(user.date_joined) : null;
  const floor = signupDate && signupDate > sevenDaysAgo ? signupDate : sevenDaysAgo;
  return toDateStr(floor);
}

export default function LogWeightForm({ onLogged, onCancel }) {
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
    if (weightKg === "") {
      setError("Enter your weight first.");
      return;
    }
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
    <form
      onSubmit={handleSubmit}
      style={{
        display: "flex",
        flexDirection: "column",
        gap: 12,
        padding: 14,
        background: "var(--bg-raised)",
        border: "1px solid var(--border-soft)",
        borderRadius: "var(--radius-md)",
      }}
    >
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))",
          gap: 12,
          alignItems: "start",
        }}
      >
        <WeightField
          required
          autoFocus
          label="Weight"
          kg={weightKg}
          onChange={setWeightKg}
          placeholder="e.g. 78.5"
          defaultUnit={unitSystem === "imperial" ? "lbs" : "kg"}
          allowToggle={false}
        />
        <DatePicker label="Date" value={loggedAt} onChange={setLoggedAt} min={minDate} max={todayStr()} />
      </div>

      <p style={{ fontSize: 12, color: "var(--text-faint)" }}>
        Up to 7 days back. Logging a date again updates that entry.
      </p>

      <ErrorBanner message={error} />

      <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
        <button
          type="button"
          className="btn btn-secondary"
          style={{ padding: "8px 14px", fontSize: 13 }}
          onClick={onCancel}
          disabled={saving}
        >
          Cancel
        </button>
        <button
          type="submit"
          className="btn btn-primary"
          style={{ padding: "8px 18px", fontSize: 13 }}
          disabled={saving}
        >
          {saving ? "Saving..." : "Save"}
        </button>
      </div>
    </form>
  );
}