import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { updateProfile } from "../api/accounts";
import PageHeader from "../components/PageHeader";
import { ErrorBanner, extractErrorMessage } from "../components/Status";

const GENDERS = [
  ["male", "Male"],
  ["female", "Female"],
  ["other", "Other"],
  ["prefer_not_to_say", "Prefer not to say"],
];
const ACTIVITY_LEVELS = [
  ["sedentary", "Sedentary"],
  ["lightly_active", "Lightly Active"],
  ["moderately_active", "Moderately Active"],
  ["very_active", "Very Active"],
];
const GOALS = [
  ["lose_weight", "Lose Weight"],
  ["gain_weight", "Gain Weight"],
  ["maintain_weight", "Maintain Weight"],
  ["gain_muscle", "Gain Muscle"],
  ["build_strength", "Build Strength"],
];
const FREQUENCIES = [
  ["1-2", "1-2 Days per week"],
  ["3-4", "3-4 Days per week"],
  ["5-6", "5-6 Days per week"],
  ["daily", "Daily"],
];
const LOCATIONS = [
  ["gym", "Gym"],
  ["home", "Home"],
  ["mixed", "Mixed"],
];
const EXPERIENCE_LEVELS = [
  ["beginner", "Beginner"],
  ["intermediate", "Intermediate"],
  ["advanced", "Advanced"],
];

// Profile fields the backend returns as plain values -- prefill the
// form directly from user.profile (already in AuthContext via getMe())
// rather than a separate fetch, since AccountSerializer already nests
// everything ProfileSerializer exposes.
function initialFormFrom(profile) {
  return {
    gender: profile.gender || "",
    dateOfBirth: profile.date_of_birth || "",
    activityLevel: profile.activity_level || "",
    currentWeightKg: profile.current_weight_kg ?? "",
    goalWeightKg: profile.goal_weight_kg ?? "",
    heightFt: profile.height_ft ?? "",
    heightIn: profile.height_in ?? "",
    primaryGoal: profile.primary_goal || "",
    medicalConditions: profile.medical_conditions || "",
    foodAllergies: profile.food_allergies || "",
    workoutFrequency: profile.workout_frequency || "",
    workoutLocation: profile.workout_location || "",
    experienceLevel: profile.experience_level || "",
  };
}

export default function EditProfile() {
  const { user, refreshUser } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState(() => initialFormFrom(user?.profile || {}));
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  const set = (field) => (e) => setForm((f) => ({ ...f, [field]: e.target.value }));

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    setSaving(true);
    try {
      await updateProfile({
        gender: form.gender,
        date_of_birth: form.dateOfBirth,
        activity_level: form.activityLevel,
        current_weight_kg: form.currentWeightKg !== "" ? Number(form.currentWeightKg) : null,
        goal_weight_kg: form.goalWeightKg !== "" ? Number(form.goalWeightKg) : null,
        height_ft: form.heightFt !== "" ? Number(form.heightFt) : null,
        height_in: form.heightIn !== "" ? Number(form.heightIn) : null,
        primary_goal: form.primaryGoal,
        medical_conditions: form.medicalConditions,
        food_allergies: form.foodAllergies,
        workout_frequency: form.workoutFrequency,
        workout_location: form.workoutLocation,
        experience_level: form.experienceLevel,
      });
      // So /profile shows the new values immediately instead of the
      // stale copy AuthContext loaded at login/last refresh.
      await refreshUser();
      navigate("/profile");
    } catch (err) {
      setError(extractErrorMessage(err, "Couldn't save. Check your details."));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="page">
      <PageHeader title="Edit Profile" back backTo="/profile" />

      <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: 14 }}>
        <div style={row2}>
          <div>
            <label>Gender</label>
            <select value={form.gender} onChange={set("gender")}>
              <option value="">Select</option>
              {GENDERS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </div>
          <div>
            <label>Date of birth</label>
            <input type="date" max={new Date().toISOString().split("T")[0]} value={form.dateOfBirth} onChange={set("dateOfBirth")} />
          </div>
        </div>

        <div style={row2}>
          <div>
            <label>Activity level</label>
            <select value={form.activityLevel} onChange={set("activityLevel")}>
              <option value="">Select</option>
              {ACTIVITY_LEVELS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </div>
          <div>
            <label>Current weight (kg)</label>
            <input type="number" step="0.1" value={form.currentWeightKg} onChange={set("currentWeightKg")} />
          </div>
        </div>

        <div style={row2}>
          <div>
            <label>Goal weight (kg)</label>
            <input type="number" step="0.1" value={form.goalWeightKg} onChange={set("goalWeightKg")} />
          </div>
          <div>
            <label>Height (ft)</label>
            <input type="number" value={form.heightFt} onChange={set("heightFt")} />
          </div>
        </div>

        <div style={row2}>
          <div>
            <label>Height (in)</label>
            <input type="number" value={form.heightIn} onChange={set("heightIn")} />
          </div>
          <div>
            <label>Primary goal</label>
            <select value={form.primaryGoal} onChange={set("primaryGoal")}>
              <option value="">Select</option>
              {GOALS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </div>
        </div>

        <div style={row2}>
          <div>
            <label>Workout frequency</label>
            <select value={form.workoutFrequency} onChange={set("workoutFrequency")}>
              <option value="">Select</option>
              {FREQUENCIES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </div>
          <div>
            <label>Workout location</label>
            <select value={form.workoutLocation} onChange={set("workoutLocation")}>
              <option value="">Select</option>
              {LOCATIONS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </div>
        </div>

        <div>
          <label>Experience level</label>
          <select value={form.experienceLevel} onChange={set("experienceLevel")}>
            <option value="">Select</option>
            {EXPERIENCE_LEVELS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </div>

        <div>
          <label>Medical conditions, injuries, or limitations (optional)</label>
          <textarea rows={2} value={form.medicalConditions} onChange={set("medicalConditions")} placeholder="Leave blank if none" />
        </div>
        <div>
          <label>Food allergies / dietary restrictions (optional)</label>
          <textarea rows={2} value={form.foodAllergies} onChange={set("foodAllergies")} placeholder="Leave blank if none" />
        </div>

        <ErrorBanner message={error} />
        <div style={row2}>
          <button type="button" className="btn btn-secondary" onClick={() => navigate("/profile")}>Cancel</button>
          <button className="btn btn-primary" disabled={saving}>{saving ? "Saving..." : "Save Changes"}</button>
        </div>
      </form>
    </div>
  );
}

const row2 = { display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 };