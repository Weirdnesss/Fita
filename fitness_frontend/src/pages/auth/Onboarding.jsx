import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../../context/AuthContext";
import { updateProfile, logWeight } from "../../api/accounts";
import HeightField from "../../components/HeightField";
import WeightField from "../../components/WeightField";
import UnitToggle from "../../components/UnitToggle";
import { ErrorBanner, extractErrorMessage } from "../../components/Status";

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

// Simple, static intro for now -- deliberately minimal so it's easy to
// turn into an actual multi-slide carousel (screenshots, animations,
// whatever) later without fighting existing state/logic.
const TUTORIAL_ITEMS = [
  ["Workouts", "Follow generated routines or build your own, then track sets as you go."],
  ["Nutrition", "Log meals and keep an eye on calories and macros against your goal."],
  ["Coach", "Ask questions and get guidance based on your own logged data."],
  ["Progress", "Weight trends and periodic reports so you can see what's working."],
];

function initialFormFrom(profile) {
  return {
    gender: profile.gender || "",
    dateOfBirth: profile.date_of_birth || "",
    activityLevel: profile.activity_level || "",
    // current_weight_kg is derived (see accounts/models.py), not stored
    // directly -- prefilled here only so the field isn't blank if they
    // already have a logged weight; submitting still logs a fresh entry.
    currentWeightKg: profile.current_weight_kg ?? "",
    goalWeightKg: profile.goal_weight_kg ?? "",
    heightCm: profile.height_cm ?? "",
    primaryGoal: profile.primary_goal || "",
    medicalConditions: profile.medical_conditions || "",
    foodAllergies: profile.food_allergies || "",
    workoutFrequency: profile.workout_frequency || "",
    workoutLocation: profile.workout_location || "",
  };
}

export default function Onboarding() {
  const { user, refreshUser } = useAuth();
  const navigate = useNavigate();
  const [step, setStep] = useState(1);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [weightUnit, setWeightUnit] = useState(() => (user?.profile?.unit_system === "imperial" ? "lbs" : "kg"));

  const [form, setForm] = useState(() => initialFormFrom(user?.profile || {}));

  const set = (field) => (e) => setForm((f) => ({ ...f, [field]: e.target.value }));

  async function handleStep1(e) {
    e.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      await updateProfile({
        gender: form.gender,
        date_of_birth: form.dateOfBirth,
        activity_level: form.activityLevel,
        goal_weight_kg: form.goalWeightKg ? Number(form.goalWeightKg) : null,
        height_cm: form.heightCm ? Number(form.heightCm) : null,
        primary_goal: form.primaryGoal,
      });
      // current_weight_kg is derived, not writable directly (see
      // ProfileSerializer) -- logging it here is what both sets the
      // baseline and gives the Weight History page a first entry to
      // show, instead of a value with no history behind it.
      if (form.currentWeightKg) {
        await logWeight({ weightKg: Number(form.currentWeightKg) });
      }
      await refreshUser();
      setStep(2);
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  async function handleStep2(e) {
    e.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      await updateProfile({
        medical_conditions: form.medicalConditions,
        food_allergies: form.foodAllergies,
        workout_frequency: form.workoutFrequency,
        workout_location: form.workoutLocation,
      });
      await refreshUser();
      setStep(3);
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-card" style={{ gap: 20 }}>
        {step < 3 && (
          <>
            <div style={{ textAlign: "center" }}>
              <div style={{ fontFamily: "var(--font-display)", fontSize: 26, color: "var(--chili)" }}>
                FITNESS ASSISTANT
              </div>
              <p style={{ color: "var(--text-dim)", fontSize: 13, marginTop: 4 }}>Set up your profile</p>
            </div>
            <StepDots step={step} />
          </>
        )}

        {step === 1 && (
          <form onSubmit={handleStep1} style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <h2>Basic information</h2>
            <div style={row2}>
              <div>
                <label>Gender</label>
                <select required value={form.gender} onChange={set("gender")}>
                  <option value="">Select</option>
                  {GENDERS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                </select>
              </div>
              <div>
                <label>Date of birth</label>
                <input type="date" required max={new Date().toISOString().split("T")[0]} value={form.dateOfBirth} onChange={set("dateOfBirth")} />
              </div>
            </div>

            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span style={{ fontSize: 13, color: "var(--text-dim)" }}>Weight unit</span>
              <UnitToggle
                options={[{ value: "kg", label: "kg" }, { value: "lbs", label: "lbs" }]}
                value={weightUnit}
                onChange={setWeightUnit}
              />
            </div>

            <div style={row2}>
              <div>
                <WeightField
                  required
                  key={weightUnit}
                  defaultUnit={weightUnit}
                  allowToggle={false}
                  label="Current weight"
                  kg={form.currentWeightKg}
                  onChange={(v) => setForm((f) => ({ ...f, currentWeightKg: v }))}
                />
              </div>
              <div>
                <WeightField
                  required
                  key={weightUnit}
                  defaultUnit={weightUnit}
                  allowToggle={false}
                  label="Goal weight"
                  kg={form.goalWeightKg}
                  onChange={(v) => setForm((f) => ({ ...f, goalWeightKg: v }))}
                />
              </div>
            </div>
            <div style={row2}>
              <div>
                <label>Activity level</label>
                <select required value={form.activityLevel} onChange={set("activityLevel")}>
                  <option value="">Select</option>
                  {ACTIVITY_LEVELS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                </select>
              </div>
              <div>
                <label>Primary goal</label>
                <select required value={form.primaryGoal} onChange={set("primaryGoal")}>
                  <option value="">Select</option>
                  {GOALS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                </select>
              </div>
            </div>
            <HeightField
              required
              defaultUnit={user?.profile?.unit_system === "imperial" ? "ftin" : "cm"}
              cm={form.heightCm}
              onChange={(cm) => setForm((f) => ({ ...f, heightCm: cm }))}
            />
            <ErrorBanner message={error} />
            <button className="btn btn-primary btn-block" disabled={submitting}>{submitting ? "Saving..." : "Continue"}</button>
          </form>
        )}

        {step === 2 && (
          <form onSubmit={handleStep2} style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <h2>Additional information</h2>
            <div>
              <label>Medical conditions, injuries, or limitations (optional)</label>
              <textarea rows={2} value={form.medicalConditions} onChange={set("medicalConditions")} placeholder="Leave blank if none" />
            </div>
            <div>
              <label>Food allergies / dietary restrictions (optional)</label>
              <textarea rows={2} value={form.foodAllergies} onChange={set("foodAllergies")} placeholder="Leave blank if none" />
            </div>
            <div>
              <label>Workout frequency</label>
              <select required value={form.workoutFrequency} onChange={set("workoutFrequency")}>
                <option value="">Select</option>
                {FREQUENCIES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
            </div>
            <div>
              <label>Workout location</label>
              <select required value={form.workoutLocation} onChange={set("workoutLocation")}>
                <option value="">Select</option>
                {LOCATIONS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
            </div>
            <ErrorBanner message={error} />
            <button className="btn btn-primary btn-block" disabled={submitting}>{submitting ? "Finishing..." : "Continue"}</button>
          </form>
        )}

        {step === 3 && (
          <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
            <div style={{ textAlign: "center" }}>
              <h2 style={{ marginBottom: 4 }}>You're all set!</h2>
              <p style={{ color: "var(--text-dim)", fontSize: 14 }}>Here's a quick look at what you can do.</p>
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              {TUTORIAL_ITEMS.map(([title, blurb]) => (
                <div key={title} style={{ borderLeft: "3px solid var(--chili)", paddingLeft: 12 }}>
                  <h3 style={{ marginBottom: 2 }}>{title}</h3>
                  <p style={{ color: "var(--text-dim)", fontSize: 13 }}>{blurb}</p>
                </div>
              ))}
            </div>

            <button className="btn btn-primary btn-block" onClick={() => navigate("/profile")}>
              Get Started
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

function StepDots({ step }) {
  return (
    <div style={{ display: "flex", justifyContent: "center", gap: 6 }}>
      {[1, 2, 3].map((n) => (
        <span
          key={n}
          style={{
            width: n === step ? 20 : 6,
            height: 6,
            borderRadius: 3,
            background: n <= step ? "var(--chili)" : "var(--border)",
            transition: "width 0.2s ease",
          }}
        />
      ))}
    </div>
  );
}

const row2 = { display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 };
