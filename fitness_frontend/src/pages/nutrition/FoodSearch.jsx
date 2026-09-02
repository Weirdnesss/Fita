import { useEffect, useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import PageHeader from "../../components/PageHeader";
import { Loading, ErrorBanner, extractErrorMessage } from "../../components/Status";
import { useToast } from "../../context/ToastContext";
import { searchFoods, logFood } from "../../api/nutrition";

const MEALS = [
  ["breakfast", "Breakfast"],
  ["lunch", "Lunch"],
  ["dinner", "Dinner"],
  ["snack", "Snack"],
];

// Mirrors nutrition.views.MAX_SERVINGS on the backend.
const MAX_SERVINGS = 50;

// Mirrors nutrition.models.FoodCategory on the backend.
const CATEGORIES = [
  ["rice_grains", "Rice & Grains"],
  ["roots_tubers", "Roots & Tubers"],
  ["nuts_legumes", "Nuts & Legumes"],
  ["viands_meat", "Meat & Poultry"],
  ["viands_fish", "Fish & Seafood"],
  ["eggs", "Eggs"],
  ["dairy", "Dairy"],
  ["fats_oils", "Fats & Oils"],
  ["vegetables", "Vegetables"],
  ["fruits", "Fruits"],
  ["soups", "Soups & Stews"],
  ["snacks", "Snacks & Merienda"],
  ["desserts", "Desserts & Sweets"],
  ["beverages", "Beverages"],
  ["condiments", "Condiments & Sauces"],
  ["other", "Other"],
];

export default function FoodSearch() {
  const navigate = useNavigate();
  const location = useLocation();
  const logDate = location.state?.date; // undefined -> backend defaults to today
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState(null);
  const [results, setResults] = useState([]);
  const [count, setCount] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState(null);

  useEffect(() => {
    const t = setTimeout(async () => {
      setLoading(true);
      try {
        const r = await searchFoods(query, category);
        setResults(r.results);
        setCount(r.count);
      } catch (err) {
        setError(extractErrorMessage(err));
      } finally {
        setLoading(false);
      }
    }, 300);
    return () => clearTimeout(t);
  }, [query, category]);

  if (selected) {
    return (
      <FoodDetail
        food={selected}
        logDate={logDate}
        onBack={() => setSelected(null)}
        onLogged={() => navigate("/nutrition")}
      />
    );
  }

  return (
    <div className="page">
      <PageHeader title="Add Food" back />
      <input autoFocus placeholder="Search for a food (e.g. adobo, rice)" value={query} onChange={(e) => setQuery(e.target.value)} />

      <div style={{ display: "flex", gap: 6, overflowX: "auto", paddingBottom: 4 }}>
        <CategoryChip active={category === null} label="All" onClick={() => setCategory(null)} />
        {CATEGORIES.map(([value, label]) => (
          <CategoryChip key={value} active={category === value} label={label} onClick={() => setCategory(category === value ? null : value)} />
        ))}
      </div>

      {loading && <Loading />}
      <ErrorBanner message={error} />
      {!loading && query.trim().length === 0 && category === null && (
        <p style={{ fontSize: 13, color: "var(--text-faint)" }}>Try "rice", "adobo", "lumpia", or pick a category above.</p>
      )}
      {!loading && results.length === 0 && (query.trim().length > 0 || category !== null) && (
        <p style={{ fontSize: 13, color: "var(--text-faint)" }}>No results{query.trim() && ` for "${query}"`}.</p>
      )}
      {!loading && results.length > 0 && count > results.length && (
        <p style={{ fontSize: 12, color: "var(--text-faint)" }}>
          Showing {results.length} of {count} -- narrow your search to see more.
        </p>
      )}
      {results.map((food) => (
        <div key={food.id} className="card" style={{ marginBottom: 8, cursor: "pointer" }} onClick={() => setSelected(food)}>
          <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
            <div>
              <p style={{ fontWeight: 600 }}>{food.name}</p>
              <p style={{ fontSize: 12, color: "var(--text-faint)" }}>
                {food.local_name ? `${food.local_name} · ` : ""}
                {food.serving_description}
              </p>
            </div>
            <div style={{ textAlign: "right", flexShrink: 0 }}>
              <span className="stat" style={{ fontSize: 14, display: "block" }}>{Math.round(food.calories)} kcal</span>
              <VerifiedBadge isVerified={food.is_verified} />
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

function CategoryChip({ active, label, onClick }) {
  return (
    <button
      onClick={onClick}
      className={active ? "btn btn-primary" : "btn btn-secondary"}
      style={{ padding: "6px 12px", fontSize: 12, whiteSpace: "nowrap", flexShrink: 0, height: "auto" }}
    >
      {label}
    </button>
  );
}

function VerifiedBadge({ isVerified }) {
  return (
    <span className={`pill ${isVerified ? "pill-bamboo" : "pill-turmeric"}`} style={{ marginTop: 4 }}>
      {isVerified ? "PhilFCT" : "Estimated"}
    </span>
  );
}

function FoodDetail({ food, logDate, onBack, onLogged }) {
  const showToast = useToast();
  // PhilFCT items are stored per-100g -- let people type grams directly
  // instead of doing "1.5 servings of 100g" math in their head. Estimated
  // dishes keep their real serving unit (e.g. "1 cup") as-is.
  const isGramBased = food.serving_description === "100g";

  const [amount, setAmount] = useState(isGramBased ? 100 : 1);
  const [mealType, setMealType] = useState("breakfast");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const servings = isGramBased ? Number(amount) / food.serving_size_g : Number(amount);
  const servingsInvalid = !Number.isFinite(servings) || servings <= 0 || servings > MAX_SERVINGS;
  const validationMessage = servingsInvalid
    ? Number(amount) > (isGramBased ? MAX_SERVINGS * food.serving_size_g : MAX_SERVINGS)
      ? `That's more than this form supports in one entry -- log it in smaller amounts.`
      : `Enter an amount greater than 0.`
    : "";

  async function handleAdd() {
    if (servingsInvalid) return;
    setSaving(true);
    setError("");
    try {
      await logFood({ foodItemId: food.id, mealType, servings, date: logDate });
      const mealLabel = MEALS.find(([v]) => v === mealType)?.[1] || mealType;
      showToast(`Added ${food.name} to ${mealLabel}`, "success");
      onLogged();
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="page">
      <PageHeader
        title={food.name}
        subtitle={food.local_name || undefined}
        back={false}
        action={<button className="btn-ghost" style={{ background: "none", border: "none" }} onClick={onBack}>Back to Search</button>}
      />

      {logDate && (
        <p style={{ fontSize: 12, color: "var(--turmeric)" }}>
          Logging to {new Date(logDate + "T00:00:00").toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" })}, not today.
        </p>
      )}

      <VerifiedBadge isVerified={food.is_verified} />

      <div className="card">
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 8, textAlign: "center" }}>
          <MacroBox label="Calories" value={Math.round(food.calories * servings)} />
          <MacroBox label="Protein" value={`${Math.round(food.protein_g * servings)}g`} />
          <MacroBox label="Carbs" value={`${Math.round(food.carbs_g * servings)}g`} />
          <MacroBox label="Fat" value={`${Math.round(food.fat_g * servings)}g`} />
        </div>
      </div>

      <div>
        <label>{isGramBased ? "Amount (g)" : `Servings (${food.serving_description} each)`}</label>
        <input
          type="number"
          step={isGramBased ? 10 : 0.25}
          min={isGramBased ? 5 : 0.25}
          max={isGramBased ? MAX_SERVINGS * food.serving_size_g : MAX_SERVINGS}
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
        />
        {validationMessage && (
          <p style={{ fontSize: 12, color: "var(--chili)", marginTop: 4 }}>{validationMessage}</p>
        )}
      </div>

      <div>
        <label>Add to meal</label>
        <select value={mealType} onChange={(e) => setMealType(e.target.value)}>
          {MEALS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
      </div>

      <ErrorBanner message={error} />
      <button className="btn btn-primary btn-block" onClick={handleAdd} disabled={saving || servingsInvalid}>
        {saving ? "Adding..." : "Add Food"}
      </button>
    </div>
  );
}

function MacroBox({ label, value }) {
  return (
    <div style={{ background: "var(--bg-raised)", borderRadius: "var(--radius-sm)", padding: "10px 4px" }}>
      <div className="stat" style={{ fontSize: 15 }}>{value}</div>
      <div className="eyebrow" style={{ marginTop: 4 }}>{label}</div>
    </div>
  );
}
