import { useEffect, useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import PageHeader from "../../components/PageHeader";
import { Loading, ErrorBanner, EmptyState, extractErrorMessage } from "../../components/Status";
import ConfirmDialog from "../../components/ConfirmDialog";
import { useToast } from "../../context/ToastContext";
import { getDailyEntry, getNutritionProfile, deleteFoodEntry, updateFoodEntry } from "../../api/nutrition";
import { getMe } from "../../api/accounts";
import DatePicker from "../../components/DatePicker";
import NutritionTrendsPanel from "./NutritionTrendsPanel";
import SettingsButton from "../../components/SettingsButton";


const MEALS = [
  ["breakfast", "Breakfast"],
  ["lunch", "Lunch"],
  ["dinner", "Dinner"],
  ["snack", "Snack"],
];

const MEAL_COLORS = {
  breakfast: "var(--turmeric)",
  lunch: "var(--bamboo)",
  dinner: "var(--ube)",
  snack: "var(--chili)",
};

// Mirrors nutrition.views.MAX_BACKDATE_DAYS on the backend -- entries
// can only be added within this window, though viewing history further
// back is still unrestricted.
const MAX_BACKDATE_DAYS = 7;

// Mirrors nutrition.views.MAX_SERVINGS on the backend.
const MAX_SERVINGS = 50;



export default function NutritionDashboard() {
  const navigate = useNavigate();
  const location = useLocation();
  const showToast = useToast();
  const [daily, setDaily] = useState(null);
  const [goals, setGoals] = useState(null);
  const [account, setAccount] = useState(null);
  const [error, setError] = useState("");
  const [selectedDate, setSelectedDate] = useState(
    () => location.state?.date || toDateStr(new Date())
  );  
  const [activeTab, setActiveTab] = useState("log"); // "log" | "trends"

  const isToday = selectedDate === toDateStr(new Date());
  const isWithinLogWindow = daysAgo(selectedDate) <= MAX_BACKDATE_DAYS;

  const accountStartDate = account?.date_joined
    ? toDateStr(new Date(account.date_joined))
    : null;

  const isOldestDate = accountStartDate
    ? selectedDate <= accountStartDate
    : false;

  useEffect(() => {
    load(selectedDate);
  }, [selectedDate]);

  async function load(date) {
    try {
      const [d, g, a] = await Promise.all([
        getDailyEntry(date),
        getNutritionProfile(),
        getMe(),
      ]);

      setDaily(d);
      setGoals(g);
      setAccount(a);
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
  const [editDate, setEditDate] = useState("");
  const [editSaving, setEditSaving] = useState(false);
  const [editError, setEditError] = useState("");

  const oldestAllowedDate = toDateStr(new Date(Date.now() - MAX_BACKDATE_DAYS * 86400000));

  function startEdit(entry) {
    const isGramBased = entry.serving_description === "100g";
    setEditingId(entry.id);
    setEditAmount(isGramBased ? entry.servings * entry.serving_size_g : entry.servings);
    setEditMeal(entry.meal_type);
    setEditDate(selectedDate);
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
    const dateChanged = editDate !== selectedDate;
    setEditSaving(true);
    setEditError("");
    try {
      await updateFoodEntry(entry.id, {
        mealType: editMeal,
        servings,
        date: dateChanged ? editDate : undefined,
      });
      setEditingId(null);
      load(selectedDate);
      showToast(dateChanged ? `Moved to ${formatDayLabel(editDate)}` : "Entry updated", "success");
    } catch (err) {
      setEditError(extractErrorMessage(err));
    } finally {
      setEditSaving(false);
    }
  }

  if (!daily || !goals || !account) {
    return (
      <div className="page">
        <PageHeader
          title="Nutrition"
          subtitle="Log and track your macros"
          action={<SettingsButton to="/nutrition/settings" label="Nutrition goals" />}
        />
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
      <PageHeader
        title="Nutrition"
        subtitle="Log and track your macros"
        action={<SettingsButton to="/nutrition/settings" label="Nutrition goals" />}
      />
      <ErrorBanner message={error} />
      <div className="tab-bar">
        <button
          className={`tab-btn${activeTab === "log" ? " active" : ""}`}
          onClick={() => setActiveTab("log")}
        >
          Log
        </button>
        <button
          className={`tab-btn${activeTab === "trends" ? " active" : ""}`}
          onClick={() => setActiveTab("trends")}
        >
          Trends
        </button>
      </div>
      {activeTab === "log" && (
      <div className="nutrition-content">
      <div
        className="nutrition-date-nav"
        style={{
          display: "flex",
          justifyContent: "center",
          alignItems: "flex-start",
          gap: 16,
          marginBottom: 8,
        }}
      >
            <button
        onClick={() => shiftDay(-1)}
        disabled={isOldestDate}
        className="btn-ghost"
        aria-label="Previous day"
        style={{
          background: "var(--bg-raised)",
          border: "1px solid var(--border-soft)",
          borderRadius: 10,
          width: 44,
          height: 44,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize: 28,
          lineHeight: 1,
          padding: 0,
          marginTop: 0,
          opacity: isOldestDate ? 0.3 : 1,
          flexShrink: 0,
        }}
      >
        ‹
      </button>

      <div style={{ textAlign: "center" }}>
        <div style={{ display: "inline-block", minWidth: 150, maxWidth: "100%" }}>
          <DatePicker
            value={selectedDate}
            onChange={setSelectedDate}
            min={accountStartDate}
            max={toDateStr(new Date())}
          />
        </div>

    <div style={{ visibility: isToday ? "hidden" : "visible" }}>
      <button
        onClick={() => setSelectedDate(toDateStr(new Date()))}
        tabIndex={isToday ? -1 : 0}
        style={{
          background: "none",
          border: "none",
          color: "var(--chili)",
          fontSize: 12,
          fontWeight: 600,
          padding: "4px 8px",
          cursor: "pointer",
        }}
      >
        Back to Today
      </button>
    </div>
  </div>

  <button
    onClick={() => shiftDay(1)}
    disabled={isToday}
    className="btn-ghost"
    aria-label="Next day"
    style={{
      background: "var(--bg-raised)",
      border: "1px solid var(--border-soft)",
      borderRadius: 10,
      width: 44,
      height: 44,
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      fontSize: 28,
      lineHeight: 1,
      padding: 0,
      marginTop: 0,
      opacity: isToday ? 0.3 : 1,
      flexShrink: 0,
    }}
  >
    ›
  </button>
</div>
      
      <div className="nutrition-top-section">
        <div className="card nutrition-summary-card">
          <div className="summary-ring">
            <CalorieRing pct={pct} isOver={isOverCalories} />
          </div>

          <div className="summary-figures">
            <div className="summary-remaining">
              <div className="stat-lg" style={isOverCalories ? { color: "var(--chili)" } : undefined}>
                {isOverCalories ? `+${Math.abs(remaining)}` : remaining}
              </div>
              <div className="eyebrow">{isOverCalories ? "Over goal" : "Remaining kcal"}</div>
            </div>
            <div className="summary-totals">
              <MacroStat label="Consumed" value={`${consumed} kcal`} color="chili" />
              <MacroStat label="Goal" value={`${goal} kcal`} color="bamboo" />
            </div>
          </div>

          <div className="summary-macros">
            <MacroProgress label="Protein" accent="bamboo"   consumed={daily.total_protein} goal={goals.daily_protein_goal} />
            <MacroProgress label="Carbs"   accent="turmeric" consumed={daily.total_carbs}   goal={goals.daily_carbs_goal} />
            <MacroProgress label="Fat"     accent="ube"      consumed={daily.total_fat}     goal={goals.daily_fat_goal} />
          </div>
        </div>
      </div>

      <div>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8, marginTop: 8 }}>
          <h3>Food Entries</h3>
          <span style={{ fontSize: 12, color: "var(--text-faint)" }}>{formatDayLabel(selectedDate)}</span>
        </div>

        <div className="nutrition-actions page-actions" style={{ display: "flex", gap: 8 }}>
          {isWithinLogWindow ? (
            <button className="btn btn-primary" style={{ flex: 1 }} onClick={() => navigate("/nutrition/search", { state: { date: selectedDate } })}>
              Add Food
            </button>
          ) : (
            <p style={{ flex: 1, fontSize: 12, color: "var(--text-faint)", display: "flex", alignItems: "center" }}>
              Logging is only available for the last {MAX_BACKDATE_DAYS} days.
            </p>
          )}
        </div>

        {daily.food_entries.length === 0 ? (
          <div className="card">
            <EmptyState title="Nothing logged yet" eyebrow={`Nothing added for ${formatDayLabel(selectedDate).toLowerCase()}`} />
          </div>
        ) : (
          <div className="nutrition-meals-grid">
            {MEALS.map(([key, label]) => {
              const entries = entriesByMeal[key];
              const mealCalories = Math.round(entries.reduce((s, e) => s + e.calories, 0));
              return (
                <div key={key} className="card card-accent" style={{ marginBottom: 14, "--accent-color": MEAL_COLORS[key] }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                    <p style={{ fontWeight: 600 }}>{label}</p>
                    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                      {entries.length > 0 && (
                        <span className="stat" style={{ fontSize: 13, color: "var(--text-dim)" }}>{mealCalories} kcal</span>
                      )}
                      {isWithinLogWindow && (
                        <button
                          className="icon-btn"
                          aria-label={`Add food to ${label}`}
                          onClick={() => navigate("/nutrition/search", { state: { date: selectedDate, mealType: key } })}
                        >
                          +
                        </button>
                      )}
                    </div>
                  </div>

                  {entries.length === 0 && (
                    <p style={{ fontSize: 12, color: "var(--text-faint)", opacity: 0.6 }}>—</p>
                  )}

                  {entries.map((e) => (
                    <div key={e.id} style={{ borderTop: "1px solid var(--border-soft)", padding: "2px 0" }}>
                      {editingId === e.id ? (
                        <div style={{ display: "flex", flexDirection: "column", gap: 8, padding: "10px 0" }}>
                          <p style={{ fontSize: 14, fontWeight: 600 }}>{e.food_name}</p>

                          {isWithinLogWindow ? (
                            <>
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
                              <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                                <div style={{ flex: 1 }}>
                                  <DatePicker value={editDate} onChange={setEditDate} min={oldestAllowedDate} max={toDateStr(new Date())} />
                                </div>
                                <button
                                  className="btn btn-secondary"
                                  style={{ flexShrink: 0 }}
                                  onClick={() => navigate("/nutrition/search", {
                                    state: { date: selectedDate, editingEntryId: e.id, editingMealType: e.meal_type },
                                  })}
                                >
                                  Change Food
                                </button>
                              </div>
                            </>
                          ) : (
                            <p style={{ fontSize: 12, color: "var(--text-faint)" }}>
                              Entries older than {MAX_BACKDATE_DAYS} days can't be edited, only removed.
                            </p>
                          )}

                          {editError && <p style={{ fontSize: 12, color: "var(--chili)" }}>{editError}</p>}

                          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                            <button
                              className="btn-ghost"
                              style={{ fontSize: 13, marginRight: "auto" }}
                              onClick={() => setPendingDelete({ id: e.id, foodName: e.food_name })}
                            >
                              Remove
                            </button>
                            <button className="btn btn-secondary" style={{ padding: "8px 14px", fontSize: 13 }} onClick={() => setEditingId(null)}>
                              {isWithinLogWindow ? "Cancel" : "Close"}
                            </button>
                            {isWithinLogWindow && (
                              <button
                                className="btn btn-primary"
                                style={{ padding: "8px 18px", fontSize: 13 }}
                                onClick={() => saveEdit(e)}
                                disabled={editSaving}
                              >
                                {editSaving ? "Saving..." : "Save"}
                              </button>
                            )}
                          </div>
                        </div>
                      ) : (
                        <div
                          className="entry-row"
                          role="button"
                          tabIndex={0}
                          onClick={() => startEdit(e)}
                          onKeyDown={(ev) => (ev.key === "Enter" || ev.key === " ") && startEdit(e)}
                          style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, padding: "10px 8px", margin: "0 -8px" }}
                        >
                          <div style={{ minWidth: 0 }}>
                            <p style={{ fontSize: 14 }}>{e.food_name}</p>
                            <p style={{ fontSize: 11, color: "var(--text-faint)", marginTop: 2 }}>
                              {e.serving_description === "100g" ? `${Math.round(e.servings * e.serving_size_g)}g` : `${e.servings}x`}
                            </p>
                          </div>
                          <span className="stat" style={{ fontSize: 13, flexShrink: 0 }}>{Math.round(e.calories)}</span>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              );
            })}
          </div>
        )}
      </div>
      </div>
      )}

      {activeTab === "trends" && <NutritionTrendsPanel />}

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



function MacroProgress({ label, consumed, goal, accent = "bamboo" }) {
  const pct = goal > 0 ? Math.min((consumed / goal) * 100, 100) : 0;
  const isOver = goal > 0 && consumed > goal;
  return (
    <div style={{ width: "100%" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 4 }}>
        <span className="eyebrow">{label}</span>
        <span className="stat" style={{ fontSize: 12, color: isOver ? "var(--chili)" : "var(--text-dim)" }}>
          {Math.round(consumed)}g / {Math.round(goal)}g
        </span>
      </div>
      <div className="progress-track">
        <div
          className="progress-fill"
          style={{ width: `${pct}%`, "--accent-color": isOver ? "var(--chili)" : `var(--${accent})` }}
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