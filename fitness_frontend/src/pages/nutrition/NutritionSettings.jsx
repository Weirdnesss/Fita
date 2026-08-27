import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import PageHeader from "../../components/PageHeader";
import { Loading, ErrorBanner, extractErrorMessage } from "../../components/Status";
import { getNutritionProfile, updateNutritionProfile, getSuggestedGoals } from "../../api/nutrition";
import { updateProfile } from "../../api/accounts";

// Mirrors NutritionProfileSerializer's bounds on the backend.
const GOAL_FIELDS = [
  ["daily_calories_goal", "Calories", "kcal", 500, 10000],
  ["daily_protein_goal", "Protein", "g", 10, 1000],
  ["daily_carbs_goal", "Carbs", "g", 10, 1000],
  ["daily_fat_goal", "Fat", "g", 10, 1000],
];

// Maps the calculator's missing_fields (accounts.Profile-shaped) to the
// small set of inputs this page shows to collect just what's missing,
// without sending the user through the whole signup wizard again.
const MISSING_FIELD_CONFIG = {
  current_weight_kg: { label: "Weight (kg)" },
  height_cm: { label: "Height" },
  age: { label: "Date of birth" },
  gender: { label: "Gender" },
};

export default function NutritionSettings() {
  const navigate = useNavigate();
  const [goals, setGoals] = useState(null);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  const [missingFields, setMissingFields] = useState(null); // null = not checked yet
  const [aboutYou, setAboutYou] = useState({
    current_weight_kg: "", height_ft: "", height_in: "", date_of_birth: "", gender: "",
  });
  const [suggestion, setSuggestion] = useState(null);
  const [calculating, setCalculating] = useState(false);
  const [calcError, setCalcError] = useState("");

  useEffect(() => {
    getNutritionProfile().then(setGoals).catch((err) => setError(extractErrorMessage(err)));
  }, []);

  async function handleAutoCalculate() {
    setCalculating(true);
    setCalcError("");
    setSuggestion(null);
    try {
      const result = await getSuggestedGoals();
      setSuggestion(result);
      setMissingFields(null);
    } catch (err) {
      if (err.response?.status === 422) {
        setMissingFields(err.response.data.missing_fields || []);
      } else {
        setCalcError(extractErrorMessage(err));
      }
    } finally {
      setCalculating(false);
    }
  }

  async function handleSaveAboutYouAndCalculate() {
    setCalculating(true);
    setCalcError("");
    try {
      const payload = {};
      if (missingFields.includes("current_weight_kg")) payload.current_weight_kg = Number(aboutYou.current_weight_kg);
      if (missingFields.includes("height_cm")) {
        payload.height_ft = Number(aboutYou.height_ft);
        payload.height_in = Number(aboutYou.height_in || 0);
      }
      if (missingFields.includes("age")) payload.date_of_birth = aboutYou.date_of_birth;
      if (missingFields.includes("gender")) payload.gender = aboutYou.gender;

      await updateProfile(payload);
      const result = await getSuggestedGoals();
      setSuggestion(result);
      setMissingFields(null);
    } catch (err) {
      setCalcError(extractErrorMessage(err));
    } finally {
      setCalculating(false);
    }
  }

  function applySuggestion() {
    setGoals((g) => ({
      ...g,
      daily_calories_goal: suggestion.calories,
      daily_protein_goal: suggestion.protein_g,
      daily_carbs_goal: suggestion.carbs_g,
      daily_fat_goal: suggestion.fat_g,
    }));
    setSuggestion(null);
  }

  function handleChange(field, value) {
    setGoals((g) => ({ ...g, [field]: value }));
  }

  async function handleSave() {
    if (goalsInvalid) return;
    setSaving(true);
    setError("");
    try {
      const updated = await updateNutritionProfile({
        daily_calories_goal: Number(goals.daily_calories_goal),
        daily_protein_goal: Number(goals.daily_protein_goal),
        daily_carbs_goal: Number(goals.daily_carbs_goal),
        daily_fat_goal: Number(goals.daily_fat_goal),
      });
      setGoals(updated);
      navigate("/nutrition");
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  if (!goals) {
    return (
      <div className="page">
        <PageHeader title="Nutrition Goals" back />
        <ErrorBanner message={error} />
        {!error && <Loading />}
      </div>
    );
  }

  // Only reachable once `goals` is loaded, so this is safe here -- it
  // was previously computed above the (!goals) guard, which crashed the
  // whole page on first render since goals starts out null.
  const goalsInvalid = GOAL_FIELDS.some(([field, , , min, max]) => {
    const v = Number(goals[field]);
    return !Number.isFinite(v) || v < min || v > max;
  });

  return (
    <div className="page">
      <PageHeader title="Nutrition Goals" subtitle="Your daily targets, used on the Nutrition dashboard" back />

      <div className="card" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div>
            <p style={{ fontWeight: 600 }}>Auto-calculate from your stats</p>
            <p style={{ fontSize: 12, color: "var(--text-faint)" }}>
              Uses your weight, height, age, activity level, and goal (Mifflin-St Jeor formula)
            </p>
          </div>
          <button className="btn btn-secondary" onClick={handleAutoCalculate} disabled={calculating}>
            {calculating ? "..." : "Calculate"}
          </button>
        </div>

        <ErrorBanner message={calcError} />

        {missingFields && missingFields.length > 0 && (
          <div style={{ display: "flex", flexDirection: "column", gap: 10, borderTop: "1px solid var(--border)", paddingTop: 12 }}>
            <p style={{ fontSize: 13 }}>We need a bit more info first:</p>
            {missingFields.includes("current_weight_kg") && (
              <div>
                <label>{MISSING_FIELD_CONFIG.current_weight_kg.label}</label>
                <input type="number" min="20" value={aboutYou.current_weight_kg}
                  onChange={(e) => setAboutYou((a) => ({ ...a, current_weight_kg: e.target.value }))} />
              </div>
            )}
            {missingFields.includes("height_cm") && (
              <div style={{ display: "flex", gap: 8 }}>
                <div style={{ flex: 1 }}>
                  <label>Height (ft)</label>
                  <input type="number" min="3" max="8" value={aboutYou.height_ft}
                    onChange={(e) => setAboutYou((a) => ({ ...a, height_ft: e.target.value }))} />
                </div>
                <div style={{ flex: 1 }}>
                  <label>Height (in)</label>
                  <input type="number" min="0" max="11" value={aboutYou.height_in}
                    onChange={(e) => setAboutYou((a) => ({ ...a, height_in: e.target.value }))} />
                </div>
              </div>
            )}
            {missingFields.includes("age") && (
              <div>
                <label>{MISSING_FIELD_CONFIG.age.label}</label>
                <input type="date" max={new Date().toISOString().split("T")[0]} value={aboutYou.date_of_birth}
                  onChange={(e) => setAboutYou((a) => ({ ...a, date_of_birth: e.target.value }))} />
              </div>
            )}
            {missingFields.includes("gender") && (
              <div>
                <label>{MISSING_FIELD_CONFIG.gender.label}</label>
                <select value={aboutYou.gender} onChange={(e) => setAboutYou((a) => ({ ...a, gender: e.target.value }))}>
                  <option value="">Select...</option>
                  <option value="male">Male</option>
                  <option value="female">Female</option>
                  <option value="other">Other</option>
                  <option value="prefer_not_to_say">Prefer not to say</option>
                </select>
              </div>
            )}
            <button className="btn btn-primary" onClick={handleSaveAboutYouAndCalculate} disabled={calculating}>
              {calculating ? "Calculating..." : "Save & Calculate"}
            </button>
          </div>
        )}

        {suggestion && (
          <div style={{ display: "flex", flexDirection: "column", gap: 8, borderTop: "1px solid var(--border)", paddingTop: 12 }}>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 8, textAlign: "center" }}>
              <SuggestionBox label="Calories" value={suggestion.calories} />
              <SuggestionBox label="Protein" value={`${suggestion.protein_g}g`} />
              <SuggestionBox label="Carbs" value={`${suggestion.carbs_g}g`} />
              <SuggestionBox label="Fat" value={`${suggestion.fat_g}g`} />
            </div>
            <p style={{ fontSize: 11, color: "var(--text-faint)" }}>
              BMR {suggestion.bmr} kcal · TDEE {suggestion.tdee} kcal
            </p>
            {suggestion.assumptions.map((a, i) => (
              <p key={i} style={{ fontSize: 11, color: "var(--turmeric)" }}>{a}</p>
            ))}
            <p style={{ fontSize: 11, color: "var(--text-faint)" }}>
              This is an estimate, not medical advice -- if you have a medical condition, check with a doctor or dietitian before following it.
            </p>
            <button className="btn btn-primary" onClick={applySuggestion}>Use These Goals</button>
          </div>
        )}
      </div>

      <div className="card" style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        {GOAL_FIELDS.map(([field, label, unit, min, max]) => {
          const v = Number(goals[field]);
          const invalid = !Number.isFinite(v) || v < min || v > max;
          return (
            <div key={field}>
              <label>{label} ({unit})</label>
              <input
                type="number"
                min={min}
                max={max}
                step={field === "daily_calories_goal" ? 50 : 5}
                value={goals[field]}
                onChange={(e) => handleChange(field, e.target.value)}
              />
              {invalid && (
                <p style={{ fontSize: 12, color: "var(--chili)", marginTop: 4 }}>
                  Must be between {min} and {max}.
                </p>
              )}
            </div>
          );
        })}

        <ErrorBanner message={error} />
        <button className="btn btn-primary btn-block" onClick={handleSave} disabled={saving || goalsInvalid}>
          {saving ? "Saving..." : "Save Goals"}
        </button>
      </div>
    </div>
  );
}

function SuggestionBox({ label, value }) {
  return (
    <div style={{ background: "var(--bg-raised)", borderRadius: "var(--radius-sm)", padding: "10px 4px" }}>
      <div className="stat" style={{ fontSize: 15 }}>{value}</div>
      <div className="eyebrow" style={{ marginTop: 4 }}>{label}</div>
    </div>
  );
}