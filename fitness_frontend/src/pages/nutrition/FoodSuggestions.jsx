import { useCallback, useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import PageHeader from "../../components/PageHeader";
import SegmentedControl from "../../components/SegmentedControl";
import { Loading, ErrorBanner, EmptyState, extractErrorMessage } from "../../components/Status";
import { useToast } from "../../context/ToastContext";
import { getFoodSuggestions, getMealSuggestions, logFood, logFoodsBulk } from "../../api/nutrition";
  import displayName from "../../lib/displayName";
import Pinned from "../../components/Pinned";

const MEALS = [
  ["breakfast", "Breakfast"],
  ["lunch", "Lunch"],
  ["dinner", "Dinner"],
  ["snack", "Snack"],
];

const MODES = [
  ["meals", "Full meals"],
  ["foods", "Single foods"],
];

const PER_PAGE = { meals: 3, foods: 4 };

// A sensible starting meal for the time of day, used when the user didn't
// arrive from a specific meal's "+" button.
function defaultMeal() {
  const hour = new Date().getHours();
  if (hour < 10) return "breakfast";
  if (hour < 15) return "lunch";
  if (hour < 18) return "snack";
  return "dinner";
}

const sourceLabel = (food) => food.source_label || (food.is_verified ? "PhilFCT" : "Estimated");

export default function FoodSuggestions() {
  const navigate = useNavigate();
  const location = useLocation();
  const showToast = useToast();
  const logDate = location.state?.date; // undefined -> today
  const [mealType, setMealType] = useState(location.state?.mealType || defaultMeal());
  const [mode, setMode] = useState("meals"); // "meals" (whole plates) | "foods" (single foods)

  const [data, setData] = useState(null); // response + the mode it was fetched for
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [addingKey, setAddingKey] = useState(null);
  const [added, setAdded] = useState({});
  // The main food of everything shown so far, so "Show different ideas" can skip them.
  const [shownIds, setShownIds] = useState([]);

  // Ignore a response that arrives after the user already switched meal/mode or asked again.
  const requestIdRef = useRef(0);

  const load = useCallback(
    async (meal, kind, exclude = []) => {
      const requestId = ++requestIdRef.current;
      setLoading(true);
      setError("");
      try {
        const r =
          kind === "meals"
            ? await getMealSuggestions({ mealType: meal, date: logDate, limit: PER_PAGE.meals, exclude })
            : await getFoodSuggestions({ mealType: meal, date: logDate, limit: PER_PAGE.foods, exclude });
        if (requestId !== requestIdRef.current) return;
        setData({ ...r, kind });
        setAdded({});
        const mainIds = kind === "meals" ? r.meals.map((m) => m.items[0].food.id) : r.suggestions.map((s) => s.food.id);
        setShownIds([...exclude, ...mainIds]);
      } catch (err) {
        if (requestId !== requestIdRef.current) return;
        setError(extractErrorMessage(err));
        setData(null);
      } finally {
        if (requestId === requestIdRef.current) setLoading(false);
      }
    },
    [logDate]
  );

  useEffect(() => {
    load(mealType, mode);
  }, [mealType, mode, load]);

  const mealLabel = MEALS.find(([v]) => v === mealType)?.[1] || mealType;
  const ready = !!data && data.kind === mode;
  const meals = ready && mode === "meals" ? data.meals : [];
  const foods = ready && mode === "foods" ? data.suggestions : [];
  const results = mode === "meals" ? meals : foods;
  const addedAny = Object.keys(added).length > 0;

  // What's left after the foods added from this page, without re-asking the
  // server (and the LLM) every time something is added.
  let left = null;
  if (ready) {
    left = { ...data.remaining };
    const addedItems =
      mode === "meals"
        ? meals.map((m, i) => (added[`m${i}`] ? m.totals : null))
        : foods.map((s) => (added[`f${s.food.id}`] ? s : null));
    for (const t of addedItems) {
      if (!t) continue;
      left.calories -= t.calories;
      left.protein_g -= t.protein_g;
      left.carbs_g -= t.carbs_g;
      left.fat_g -= t.fat_g;
    }
    for (const k of Object.keys(left)) left[k] = Math.max(left[k], 0);
  }

  async function handleAddFood(s) {
    const key = `f${s.food.id}`;
    setAddingKey(key);
    setError("");
    try {
      await logFood({ foodItemId: s.food.id, mealType, servings: s.servings, date: logDate });
      setAdded((prev) => ({ ...prev, [key]: true }));
      showToast(`Added ${displayName(s.food.name)} to ${mealLabel}`, "success");
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setAddingKey(null);
    }
  }

  async function handleAddMeal(meal, index) {
    const key = `m${index}`;
    setAddingKey(key);
    setError("");
    try {
      await logFoodsBulk({
        mealType,
        date: logDate,
        items: meal.items.map((i) => ({ foodItemId: i.food.id, servings: i.servings })),
      });
      setAdded((prev) => ({ ...prev, [key]: true }));
      showToast(`Added ${meal.items.length} foods to ${mealLabel}`, "success");
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setAddingKey(null);
    }
  }

  function handleAdjust(s) {
    // Open the normal food screen so the amount can be changed first.
    navigate("/nutrition/search", { state: { date: logDate, mealType, openFood: s.food } });
  }

  function handleMealChange(meal) {
    if (meal === mealType) return;
    setShownIds([]);
    setMealType(meal);
  }

  function handleModeChange(next) {
    if (next === mode) return;
    setShownIds([]);
    setMode(next);
  }

  return (
    <div className="page">
      <PageHeader title="Meal Ideas" subtitle="Foods that fit what you have left today" back />

      <Pinned>
        <SegmentedControl options={MEALS} value={mealType} onChange={handleMealChange} />
        <SegmentedControl options={MODES} value={mode} onChange={handleModeChange} />
      </Pinned>

      {left && (
        <div className="card">
          <p className="eyebrow" style={{ marginBottom: 8 }}>Left for today</p>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 8, textAlign: "center" }}>
            <Stat label="Calories" value={Math.round(left.calories)} accent="chili" />
            <Stat label="Protein" value={`${Math.round(left.protein_g)}g`} accent="bamboo" />
            <Stat label="Carbs" value={`${Math.round(left.carbs_g)}g`} accent="turmeric" />
            <Stat label="Fat" value={`${Math.round(left.fat_g)}g`} accent="ube" />
          </div>
        </div>
      )}
      
      <ErrorBanner message={error} />
      {loading && <Loading label="Finding ideas" />}

      {!loading && ready && results.length === 0 && (
        <div className="card">
          <EmptyState
            title={data.message || "No ideas right now."}
            action={
              <div style={{ display: "flex", gap: 8, justifyContent: "center", flexWrap: "wrap" }}>
                {shownIds.length > 0 && (
                  <button className="btn btn-secondary" onClick={() => load(mealType, mode)}>
                    Start over
                  </button>
                )}
                {mode === "meals" && (
                  <button className="btn btn-secondary" onClick={() => handleModeChange("foods")}>
                    See single foods
                  </button>
                )}
              </div>
            }
          />
        </div>
      )}

      {!loading && meals.length > 0 && (
        <div className="food-search-results-grid">
          {meals.map((meal, index) => {
            const key = `m${index}`;
            const done = !!added[key];
            return (
              <div
                key={key}
                className="card card-accent"
                style={{ marginBottom: 8, "--accent-color": "var(--bamboo)" }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 4 }}>
                  <span className="eyebrow">Option {index + 1}</span>
                  <span className="stat" style={{ fontSize: 14 }}>{Math.round(meal.totals.calories)} kcal</span>
                </div>

                {meal.items.map((item) => (
                  <div
                    key={item.food.id}
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      gap: 8,
                      padding: "8px 0",
                      borderTop: "1px solid var(--border-soft)",
                    }}
                  >
                    <div style={{ minWidth: 0 }}>
                      <p style={{ fontWeight: 600, fontSize: 14 }}>{displayName(item.food.name)}</p>
                      <p style={{ fontSize: 12, color: "var(--text-faint)" }}>
                        {item.amount_label} · {sourceLabel(item.food)}
                      </p>
                    </div>
                    <span className="stat" style={{ fontSize: 13, color: "var(--text-dim)", flexShrink: 0 }}>
                      {Math.round(item.calories)} kcal
                    </span>
                  </div>
                ))}

                <p style={{ fontSize: 12, color: "var(--text-dim)", margin: "8px 0 4px" }}>
                  Total: Protein {Math.round(meal.totals.protein_g)}g · Carbs {Math.round(meal.totals.carbs_g)}g · Fat{" "}
                  {Math.round(meal.totals.fat_g)}g
                </p>
                <p style={{ fontSize: 13 }}>{meal.reason}</p>

                <button
                  className="btn btn-primary btn-block"
                  style={{ marginTop: 12 }}
                  onClick={() => handleAddMeal(meal, index)}
                  disabled={done || addingKey !== null}
                >
                  {done ? "Added" : addingKey === key ? "Adding..." : `Add all to ${mealLabel}`}
                </button>
              </div>
            );
          })}
        </div>
      )}

      {!loading && foods.length > 0 && (
        <div className="food-search-results-grid">
          {foods.map((s) => {
            const key = `f${s.food.id}`;
            const done = !!added[key];
            return (
              <div
                key={key}
                className="card card-accent"
                style={{ marginBottom: 8, "--accent-color": "var(--bamboo)" }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
                  <div style={{ minWidth: 0 }}>
                    <p style={{ fontWeight: 600 }}>{displayName(s.food.name)}</p>
                    <p style={{ fontSize: 12, color: "var(--text-faint)" }}>{s.amount_label}</p>
                  </div>
                  <div style={{ textAlign: "right", flexShrink: 0 }}>
                    <span className="stat" style={{ fontSize: 14, display: "block" }}>
                      {Math.round(s.calories)} kcal
                    </span>
                    <span className={`pill ${s.food.is_verified ? "pill-bamboo" : "pill-neutral"}`} style={{ marginTop: 4 }}>
                      {sourceLabel(s.food)}
                    </span>
                  </div>
                </div>

                <p style={{ fontSize: 12, color: "var(--text-dim)", margin: "8px 0 4px" }}>
                  Protein {Math.round(s.protein_g)}g · Carbs {Math.round(s.carbs_g)}g · Fat {Math.round(s.fat_g)}g
                </p>
                <p style={{ fontSize: 13 }}>{s.reason}</p>

                <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
                  <button
                    className="btn btn-primary"
                    style={{ flex: 1 }}
                    onClick={() => handleAddFood(s)}
                    disabled={done || addingKey !== null}
                  >
                    {done ? "Added" : addingKey === key ? "Adding..." : `Add to ${mealLabel}`}
                  </button>
                  <button className="btn btn-secondary" onClick={() => handleAdjust(s)} disabled={done}>
                    Adjust
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {!loading && results.length > 0 && (
        <>
          <Pinned bottom className="page-actions" style={{ flexDirection: "row" }}>
            <button className="btn btn-secondary" style={{ flex: 1 }} onClick={() => load(mealType, mode, shownIds)}>
              Show different ideas
            </button>
            {addedAny && (
              <button
                className="btn btn-primary"
                style={{ flex: 1 }}
                onClick={() => navigate("/nutrition", { state: { date: logDate } })}
              >
                Done
              </button>
            )}
          </Pinned>
          <p style={{ fontSize: 12, color: "var(--text-faint)" }}>
            Every food here comes from the Fita food database. The AI only helps pick and explain them, and the
            numbers are never changed.
          </p>
        </>
      )}
    </div>
  );
}

function Stat({ label, value, accent }) {
  return (
    <div style={{ background: "var(--bg-raised)", borderRadius: "var(--radius-sm)", padding: "10px 4px" }}>
      <div className="stat" style={{ fontSize: 15, color: `var(--${accent})` }}>{value}</div>
      <div className="eyebrow" style={{ marginTop: 4 }}>{label}</div>
    </div>
  );
}
