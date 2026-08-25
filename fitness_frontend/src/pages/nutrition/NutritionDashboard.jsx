import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import PageHeader from "../../components/PageHeader";
import { Loading, ErrorBanner, extractErrorMessage } from "../../components/Status";
import { getDailyEntry, getNutritionProfile, deleteFoodEntry } from "../../api/nutrition";

const MEALS = [
  ["breakfast", "Breakfast"],
  ["lunch", "Lunch"],
  ["dinner", "Dinner"],
  ["snack", "Snack"],
];

export default function NutritionDashboard() {
  const navigate = useNavigate();
  const [daily, setDaily] = useState(null);
  const [goals, setGoals] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    load();
  }, []);

  async function load() {
    try {
      const [d, g] = await Promise.all([getDailyEntry(), getNutritionProfile()]);
      setDaily(d);
      setGoals(g);
    } catch (err) {
      setError(extractErrorMessage(err));
    }
  }

  async function handleDeleteEntry(id) {
    try {
      await deleteFoodEntry(id);
      load();
    } catch (err) {
      setError(extractErrorMessage(err));
    }
  }

  if (!daily || !goals) {
    return (
      <div className="page">
        <PageHeader title="Nutrition" subtitle="Log and track your macros" />
        <ErrorBanner message={error} />
        {!error && <Loading />}
      </div>
    );
  }

  const consumed = Math.round(daily.total_calories);
  const goal = goals.daily_calories_goal;
  const remaining = Math.max(goal - consumed, 0);
  const pct = Math.min((consumed / goal) * 100, 100);

  const entriesByMeal = MEALS.reduce((acc, [key]) => {
    acc[key] = daily.food_entries.filter((e) => e.meal_type === key);
    return acc;
  }, {});

  return (
    <div className="page">
      <PageHeader title="Nutrition" subtitle="Log and track your macros" />
      <ErrorBanner message={error} />

      <div className="card" style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 12 }}>
        <CalorieRing pct={pct} />
        <div style={{ textAlign: "center" }}>
          <div className="stat-lg">{remaining}</div>
          <div className="eyebrow">Remaining kcal</div>
        </div>
        <div style={{ display: "flex", gap: 24 }}>
          <MacroStat label="Consumed" value={`${consumed} kcal`} color="chili" />
          <MacroStat label="Goal" value={`${goal} kcal`} color="bamboo" />
        </div>
        <div style={{ display: "flex", gap: 20, marginTop: 4 }}>
          <MacroStat small label="Protein" value={`${Math.round(daily.total_protein)}g`} />
          <MacroStat small label="Carbs" value={`${Math.round(daily.total_carbs)}g`} />
          <MacroStat small label="Fat" value={`${Math.round(daily.total_fat)}g`} />
        </div>
      </div>

      <div>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
          <h3>Food Entries</h3>
          <span style={{ fontSize: 12, color: "var(--text-faint)" }}>{new Date().toLocaleDateString()}</span>
        </div>
        {MEALS.map(([key, label]) => (
          <div key={key} className="card" style={{ marginBottom: 10 }}>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8 }}>
              <p style={{ fontWeight: 600 }}>{label}</p>
              <span className="pill pill-chili">
                {Math.round(entriesByMeal[key].reduce((s, e) => s + e.calories, 0))}
              </span>
            </div>
            {entriesByMeal[key].length === 0 && (
              <p style={{ fontSize: 13, color: "var(--text-faint)" }}>No foods added</p>
            )}
            {entriesByMeal[key].map((e) => (
              <div key={e.id} style={{ display: "flex", justifyContent: "space-between", padding: "6px 0", borderTop: "1px solid var(--border-soft)" }}>
                <div>
                  <p style={{ fontSize: 14 }}>{e.food_name}</p>
                  <p style={{ fontSize: 11, color: "var(--text-faint)" }}>{e.servings}x · {Math.round(e.calories)} kcal</p>
                </div>
                <button onClick={() => handleDeleteEntry(e.id)} style={{ background: "none", border: "none", color: "var(--text-faint)", fontSize: 12 }}>
                  Remove
                </button>
              </div>
            ))}
          </div>
        ))}
        <button className="btn btn-primary btn-block" onClick={() => navigate("/nutrition/search")}>
          Add Food
        </button>
      </div>
    </div>
  );
}

function CalorieRing({ pct }) {
  const r = 52;
  const c = 2 * Math.PI * r;
  const offset = c - (pct / 100) * c;
  return (
    <svg width="130" height="130" viewBox="0 0 130 130">
      <circle cx="65" cy="65" r={r} fill="none" stroke="var(--bg-raised)" strokeWidth="10" />
      <circle
        cx="65"
        cy="65"
        r={r}
        fill="none"
        stroke="var(--chili)"
        strokeWidth="10"
        strokeDasharray={c}
        strokeDashoffset={offset}
        strokeLinecap="round"
        transform="rotate(-90 65 65)"
      />
    </svg>
  );
}

function MacroStat({ label, value, color, small }) {
  return (
    <div style={{ textAlign: "center" }}>
      <div className="stat" style={{ fontSize: small ? 14 : 16, color: color ? `var(--${color})` : "var(--text)" }}>{value}</div>
      <div className="eyebrow">{label}</div>
    </div>
  );
}
