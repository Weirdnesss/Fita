import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import PageHeader from "../../components/PageHeader";
import { Loading, ErrorBanner, extractErrorMessage } from "../../components/Status";
import ConfirmDialog from "../../components/ConfirmDialog";
import { useToast } from "../../context/ToastContext";
import { getDailyEntry, getNutritionProfile, deleteFoodEntry, updateFoodEntry } from "../../api/nutrition";

const MEALS = [
  ["breakfast", "Breakfast"],
  ["lunch", "Lunch"],
  ["dinner", "Dinner"],
  ["snack", "Snack"],
];

// Mirrors nutrition.views.MAX_BACKDATE_DAYS on the backend -- entries
// can only be added within this window, though viewing history further
// back is still unrestricted.
const MAX_BACKDATE_DAYS = 7;

// Mirrors nutrition.views.MAX_SERVINGS on the backend.
const MAX_SERVINGS = 50;

export default function NutritionDashboard() {
  const navigate = useNavigate();
  const showToast = useToast();
  const [daily, setDaily] = useState(null);
  const [goals, setGoals] = useState(null);
  const [error, setError] = useState("");
  const [selectedDate, setSelectedDate] = useState(() => toDateStr(new Date()));

  const isToday = selectedDate === toDateStr(new Date());
  const isWithinLogWindow = daysAgo(selectedDate) <= MAX_BACKDATE_DAYS;

  useEffect(() => {
    load(selectedDate);
  }, [selectedDate]);

  async function load(date) {
    try {
      const [d, g] = await Promise.all([getDailyEntry(date), getNutritionProfile()]);
      setDaily(d);
      setGoals(g);
    } catch (err) {
      setError(extractErrorMessage(err));
    }
  }

  function shiftDay(delta) {
    const d = new Date(selectedDate + "T00:00:00");
    d.setDate(d.getDate() + delta);
    setSelectedDate(toDateStr(d));
  }

  const [pendingDelete, setPendingDelete] = useState(null); // { id, foodName } | null

  async function confirmDelete() {
    const { id, foodName } = pendingDelete;
    setPendingDelete(null);
    try {
      await deleteFoodEntry(id);
      load(selectedDate);
      showToast(`Removed "${foodName}"`, "success");
    } catch (err) {
      showToast(extractErrorMessage(err), "error");
    }
  }

  const [editingId, setEditingId] = useState(null);
  const [editAmount, setEditAmount] = useState("");
  const [editMeal, setEditMeal] = useState("");
  const [editSaving, setEditSaving] = useState(false);
  const [editError, setEditError] = useState("");

  function startEdit(entry) {
    const isGramBased = entry.serving_description === "100g";
    setEditingId(entry.id);
    setEditAmount(isGramBased ? entry.servings * entry.serving_size_g : entry.servings);
    setEditMeal(entry.meal_type);
    setEditError("");
  }

  function editServingsFor(entry) {
    const isGramBased = entry.serving_description === "100g";
    return isGramBased ? Number(editAmount) / entry.serving_size_g : Number(editAmount);
  }

  async function saveEdit(entry) {
    const servings = editServingsFor(entry);
    if (!Number.isFinite(servings) || servings <= 0 || servings > MAX_SERVINGS) {
      setEditError("Enter a valid amount before saving.");
      return;
    }
    setEditSaving(true);
    setEditError("");
    try {
      await updateFoodEntry(entry.id, { mealType: editMeal, servings });
      setEditingId(null);
      load(selectedDate);
      showToast("Entry updated", "success");
    } catch (err) {
      setEditError(extractErrorMessage(err));
    } finally {
      setEditSaving(false);
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
  const isOverCalories = consumed > goal;
  const remaining = goal - consumed; // negative when over -- shown explicitly below, not hidden
  const pct = Math.min((consumed / goal) * 100, 100);

  const entriesByMeal = MEALS.reduce((acc, [key]) => {
    acc[key] = daily.food_entries.filter((e) => e.meal_type === key);
    return acc;
  }, {});

  return (
    <div className="page">
      <PageHeader title="Nutrition" subtitle="Log and track your macros" />
      <ErrorBanner message={error} />

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <button onClick={() => shiftDay(-1)} className="btn-ghost" style={{ background: "none", border: "none", fontSize: 18, padding: "4px 10px" }}>
          ‹
        </button>
        <div style={{ textAlign: "center" }}>
          <p style={{ fontWeight: 600, fontSize: 14 }}>{formatDayLabel(selectedDate)}</p>
          {!isToday && (
            <button onClick={() => setSelectedDate(toDateStr(new Date()))} style={{ background: "none", border: "none", color: "var(--chili)", fontSize: 11 }}>
              Back to Today
            </button>
          )}
        </div>
        <button onClick={() => shiftDay(1)} disabled={isToday} className="btn-ghost" style={{ background: "none", border: "none", fontSize: 18, padding: "4px 10px", opacity: isToday ? 0.3 : 1 }}>
          ›
        </button>
      </div>

      <div className="card" style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 12 }}>
        <CalorieRing pct={pct} isOver={isOverCalories} />
        <div style={{ textAlign: "center" }}>
          <div className="stat-lg" style={isOverCalories ? { color: "var(--chili)" } : undefined}>
            {isOverCalories ? `+${Math.abs(remaining)}` : remaining}
          </div>
          <div className="eyebrow">{isOverCalories ? "Over goal" : "Remaining kcal"}</div>
        </div>
        <div style={{ display: "flex", gap: 24 }}>
          <MacroStat label="Consumed" value={`${consumed} kcal`} color="chili" />
          <MacroStat label="Goal" value={`${goal} kcal`} color="bamboo" />
        </div>
        <div style={{ width: "100%", display: "flex", flexDirection: "column", gap: 10, marginTop: 4 }}>
          <MacroProgress label="Protein" consumed={daily.total_protein} goal={goals.daily_protein_goal} />
          <MacroProgress label="Carbs" consumed={daily.total_carbs} goal={goals.daily_carbs_goal} />
          <MacroProgress label="Fat" consumed={daily.total_fat} goal={goals.daily_fat_goal} />
        </div>
      </div>

      <div>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
          <h3>Food Entries</h3>
          <span style={{ fontSize: 12, color: "var(--text-faint)" }}>{formatDayLabel(selectedDate)}</span>
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
              <div key={e.id} style={{ padding: "6px 0", borderTop: "1px solid var(--border-soft)" }}>
                {editingId === e.id ? (
                  <div style={{ display: "flex", flexDirection: "column", gap: 8, padding: "4px 0" }}>
                    <p style={{ fontSize: 14 }}>{e.food_name}</p>
                    <div style={{ display: "flex", gap: 8 }}>
                      <input
                        type="number"
                        step={e.serving_description === "100g" ? 10 : 0.25}
                        min={e.serving_description === "100g" ? 5 : 0.25}
                        max={e.serving_description === "100g" ? MAX_SERVINGS * e.serving_size_g : MAX_SERVINGS}
                        value={editAmount}
                        onChange={(ev) => setEditAmount(ev.target.value)}
                        style={{ flex: 1 }}
                        placeholder={e.serving_description === "100g" ? "Amount (g)" : "Servings"}
                      />
                      <select value={editMeal} onChange={(ev) => setEditMeal(ev.target.value)} style={{ flex: 1 }}>
                        {MEALS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                      </select>
                    </div>
                    {editError && <p style={{ fontSize: 12, color: "var(--chili)" }}>{editError}</p>}
                    <div style={{ display: "flex", gap: 8 }}>
                      <button className="btn btn-primary" style={{ flex: 1 }} onClick={() => saveEdit(e)} disabled={editSaving}>
                        {editSaving ? "Saving..." : "Save"}
                      </button>
                      <button className="btn btn-secondary" onClick={() => setEditingId(null)}>Cancel</button>
                    </div>
                  </div>
                ) : (
                  <div style={{ display: "flex", justifyContent: "space-between" }}>
                    <div>
                      <p style={{ fontSize: 14 }}>{e.food_name}</p>
                      <p style={{ fontSize: 11, color: "var(--text-faint)" }}>
                        {e.serving_description === "100g" ? `${Math.round(e.servings * e.serving_size_g)}g` : `${e.servings}x`} · {Math.round(e.calories)} kcal
                      </p>
                    </div>
                    <div style={{ display: "flex", gap: 12 }}>
                      {isWithinLogWindow && (
                        <button onClick={() => startEdit(e)} style={{ background: "none", border: "none", color: "var(--text-faint)", fontSize: 12 }}>
                          Edit
                        </button>
                      )}
                      <button onClick={() => setPendingDelete({ id: e.id, foodName: e.food_name })} style={{ background: "none", border: "none", color: "var(--text-faint)", fontSize: 12 }}>
                        Remove
                      </button>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        ))}
        <div style={{ display: "flex", gap: 8 }}>
          {isWithinLogWindow ? (
            <button className="btn btn-primary" style={{ flex: 1 }} onClick={() => navigate("/nutrition/search", { state: { date: selectedDate } })}>
              Add Food
            </button>
          ) : (
            <p style={{ flex: 1, fontSize: 12, color: "var(--text-faint)", display: "flex", alignItems: "center" }}>
              Logging is only available for the last {MAX_BACKDATE_DAYS} days.
            </p>
          )}
          <button className="btn btn-secondary" onClick={() => navigate("/nutrition/settings")}>
            Goals
          </button>
        </div>
      </div>

      <ConfirmDialog
        open={!!pendingDelete}
        title="Remove food entry"
        message={pendingDelete ? `Remove "${pendingDelete.foodName}" from this log?` : ""}
        confirmLabel="Remove"
        onConfirm={confirmDelete}
        onCancel={() => setPendingDelete(null)}
      />
    </div>
  );
}

function toDateStr(date) {
  // Local calendar date as YYYY-MM-DD, not UTC (toISOString would shift
  // the date near midnight for users west of UTC, e.g. most of the day
  // in the Philippines is still "today" there but "tomorrow" in UTC).
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

function daysAgo(dateStr) {
  const date = new Date(dateStr + "T00:00:00");
  const today = new Date(toDateStr(new Date()) + "T00:00:00");
  return Math.round((today - date) / 86400000);
}

function formatDayLabel(dateStr) {
  const date = new Date(dateStr + "T00:00:00");
  const today = toDateStr(new Date());
  const yesterday = toDateStr(new Date(Date.now() - 86400000));
  if (dateStr === today) return "Today";
  if (dateStr === yesterday) return "Yesterday";
  return date.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" });
}

function CalorieRing({ pct, isOver }) {
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
        stroke={isOver ? "var(--chili)" : "var(--bamboo)"}
        strokeWidth="10"
        strokeDasharray={c}
        strokeDashoffset={offset}
        strokeLinecap="round"
        transform="rotate(-90 65 65)"
      />
    </svg>
  );
}

function MacroProgress({ label, consumed, goal }) {
  const pct = Math.min((consumed / goal) * 100, 100);
  const isOver = consumed > goal;
  return (
    <div style={{ width: "100%" }}>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, marginBottom: 4 }}>
        <span style={{ color: "var(--text-dim)" }}>{label}</span>
        <span style={{ color: isOver ? "var(--chili)" : "var(--text-dim)" }}>
          {Math.round(consumed)}g / {Math.round(goal)}g
        </span>
      </div>
      <div className="progress-track">
        <div
          className="progress-fill"
          style={{ width: `${pct}%`, "--accent-color": isOver ? "var(--chili)" : "var(--bamboo)" }}
        />
      </div>
    </div>
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
