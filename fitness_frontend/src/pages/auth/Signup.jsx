import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../../context/AuthContext";
import { register, updateProfile } from "../../api/accounts";
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
const EXPERIENCE_LEVELS = [
  ["beginner", "Beginner"],
  ["intermediate", "Intermediate"],
  ["advanced", "Advanced"],
];

export default function Signup() {
  const { login, refreshUser } = useAuth();
  const navigate = useNavigate();
  const [step, setStep] = useState(1);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const [form, setForm] = useState({
    firstName: "",
    lastName: "",
    email: "",
    password: "",
    confirmPassword: "",
    gender: "",
    dateOfBirth: "",
    activityLevel: "",
    currentWeightKg: "",
    goalWeightKg: "",
    heightFt: "",
    heightIn: "",
    primaryGoal: "",
    medicalConditions: "",
    foodAllergies: "",
    workoutFrequency: "",
    workoutLocation: "",
    experienceLevel: "",
  });

  const set = (field) => (e) => setForm((f) => ({ ...f, [field]: e.target.value }));

  async function handleStep1(e) {
    e.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      await register({
        email: form.email,
        firstName: form.firstName,
        lastName: form.lastName,
        password: form.password,
        confirmPassword: form.confirmPassword,
      });
      // Log in immediately so Steps 2 & 3 can PATCH the profile.
      await login({ email: form.email, password: form.password });
      setStep(2);
    } catch (err) {
      setError(extractErrorMessage(err, "Couldn't create your account. Check your details."));
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
        gender: form.gender,
        date_of_birth: form.dateOfBirth,
        activity_level: form.activityLevel,
        current_weight_kg: form.currentWeightKg ? Number(form.currentWeightKg) : null,
        goal_weight_kg: form.goalWeightKg ? Number(form.goalWeightKg) : null,
        height_ft: form.heightFt ? Number(form.heightFt) : null,
        height_in: form.heightIn ? Number(form.heightIn) : null,
        primary_goal: form.primaryGoal,
      });
      await refreshUser();
      setStep(3);
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  async function handleStep3(e) {
    e.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      await updateProfile({
        medical_conditions: form.medicalConditions,
        food_allergies: form.foodAllergies,
        workout_frequency: form.workoutFrequency,
        workout_location: form.workoutLocation,
        experience_level: form.experienceLevel,
      });
      await refreshUser();
      navigate("/profile");
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="page" style={{ gap: 20 }}>
      <div style={{ textAlign: "center" }}>
        <div style={{ fontFamily: "var(--font-display)", fontSize: 26, color: "var(--chili)" }}>
          FITNESS ASSISTANT
        </div>
        <p style={{ color: "var(--text-dim)", fontSize: 13, marginTop: 4 }}>Step {step} of 3</p>
      </div>
      <StepDots step={step} />

      {step === 1 && (
        <form onSubmit={handleStep1} style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <h2>Create an account</h2>
          <div style={row2}>
            <div>
              <label>First name</label>
              <input required value={form.firstName} onChange={set("firstName")} placeholder="John" />
            </div>
            <div>
              <label>Last name</label>
              <input required value={form.lastName} onChange={set("lastName")} placeholder="Doe" />
            </div>
          </div>
          <div>
            <label>Email</label>
            <input type="email" required value={form.email} onChange={set("email")} placeholder="john.doe@example.com" />
          </div>
          <div>
            <label>Password</label>
            <input type="password" required minLength={8} value={form.password} onChange={set("password")} placeholder="At least 8 characters" />
          </div>
          <div>
            <label>Confirm password</label>
            <input type="password" required minLength={8} value={form.confirmPassword} onChange={set("confirmPassword")} />
          </div>
          <ErrorBanner message={error} />
          <button className="btn btn-primary btn-block" disabled={submitting}>
            {submitting ? "Creating account..." : "Continue"}
          </button>
          <p style={{ textAlign: "center", color: "var(--text-dim)", fontSize: 14 }}>
            Already have an account? <Link to="/login" style={{ color: "var(--chili)", fontWeight: 600 }}>Sign in</Link>
          </p>
        </form>
      )}

      {step === 2 && (
        <form onSubmit={handleStep2} style={{ display: "flex", flexDirection: "column", gap: 14 }}>
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
          <div style={row2}>
            <div>
              <label>Activity level</label>
              <select required value={form.activityLevel} onChange={set("activityLevel")}>
                <option value="">Select</option>
                {ACTIVITY_LEVELS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
            </div>
            <div>
              <label>Current weight (kg)</label>
              <input type="number" step="0.1" required value={form.currentWeightKg} onChange={set("currentWeightKg")} />
            </div>
          </div>
          <div style={row2}>
            <div>
              <label>Goal weight (kg)</label>
              <input type="number" step="0.1" required value={form.goalWeightKg} onChange={set("goalWeightKg")} />
            </div>
            <div>
              <label>Height (ft)</label>
              <input type="number" required value={form.heightFt} onChange={set("heightFt")} />
            </div>
          </div>
          <div style={row2}>
            <div>
              <label>Height (in)</label>
              <input type="number" required value={form.heightIn} onChange={set("heightIn")} />
            </div>
            <div>
              <label>Primary goal</label>
              <select required value={form.primaryGoal} onChange={set("primaryGoal")}>
                <option value="">Select</option>
                {GOALS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
            </div>
          </div>
          <ErrorBanner message={error} />
          <div style={row2}>
            <button type="button" className="btn btn-secondary" onClick={() => setStep(1)}>Back</button>
            <button className="btn btn-primary" disabled={submitting}>{submitting ? "Saving..." : "Continue"}</button>
          </div>
        </form>
      )}

      {step === 3 && (
        <form onSubmit={handleStep3} style={{ display: "flex", flexDirection: "column", gap: 14 }}>
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
          <div>
            <label>Experience level</label>
            <select required value={form.experienceLevel} onChange={set("experienceLevel")}>
              <option value="">Select</option>
              {EXPERIENCE_LEVELS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </div>
          <ErrorBanner message={error} />
          <div style={row2}>
            <button type="button" className="btn btn-secondary" onClick={() => setStep(2)}>Back</button>
            <button className="btn btn-primary" disabled={submitting}>{submitting ? "Finishing..." : "Create Account"}</button>
          </div>
        </form>
      )}
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