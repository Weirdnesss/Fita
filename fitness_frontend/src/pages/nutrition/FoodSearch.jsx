import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import PageHeader from "../../components/PageHeader";
import { Loading, ErrorBanner, extractErrorMessage } from "../../components/Status";
import { searchFoods, logFood } from "../../api/nutrition";

const MEALS = [
  ["breakfast", "Breakfast"],
  ["lunch", "Lunch"],
  ["dinner", "Dinner"],
  ["snack", "Snack"],
];

export default function FoodSearch() {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState(null);

  useEffect(() => {
    const t = setTimeout(async () => {
      setLoading(true);
      try {
        const r = await searchFoods(query);
        setResults(r);
      } catch (err) {
        setError(extractErrorMessage(err));
      } finally {
        setLoading(false);
      }
    }, 300);
    return () => clearTimeout(t);
  }, [query]);

  if (selected) {
    return <FoodDetail food={selected} onBack={() => setSelected(null)} onLogged={() => navigate("/nutrition")} />;
  }

  return (
    <div className="page">
      <PageHeader title="Add Food" back />
      <input autoFocus placeholder="Search for a food (e.g. adobo, rice)" value={query} onChange={(e) => setQuery(e.target.value)} />
      {query.trim().length === 0 && (
        <p style={{ fontSize: 13, color: "var(--text-faint)" }}>Try "rice", "adobo", "lumpia"...</p>
      )}
      {loading && <Loading />}
      <ErrorBanner message={error} />
      {!loading && query.trim().length > 0 && results.length === 0 && (
        <p style={{ fontSize: 13, color: "var(--text-faint)" }}>No results for "{query}".</p>
      )}
      {results.map((food) => (
        <div key={food.id} className="card" style={{ marginBottom: 8, cursor: "pointer" }} onClick={() => setSelected(food)}>
          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <div>
              <p style={{ fontWeight: 600 }}>{food.name}</p>
              <p style={{ fontSize: 12, color: "var(--text-faint)" }}>{food.serving_description}</p>
            </div>
            <span className="stat" style={{ fontSize: 14 }}>{Math.round(food.calories)} kcal</span>
          </div>
        </div>
      ))}
    </div>
  );
}

function FoodDetail({ food, onBack, onLogged }) {
  const [servings, setServings] = useState(1);
  const [mealType, setMealType] = useState("breakfast");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function handleAdd() {
    setSaving(true);
    setError("");
    try {
      await logFood({ foodItemId: food.id, mealType, servings: Number(servings) });
      onLogged();
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="page">
      <PageHeader title={food.name} back={false} action={<button className="btn-ghost" style={{ background: "none", border: "none" }} onClick={onBack}>Back to Search</button>} />

      <div className="card">
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 8, textAlign: "center" }}>
          <MacroBox label="Calories" value={Math.round(food.calories * servings)} />
          <MacroBox label="Protein" value={`${Math.round(food.protein_g * servings)}g`} />
          <MacroBox label="Carbs" value={`${Math.round(food.carbs_g * servings)}g`} />
          <MacroBox label="Fat" value={`${Math.round(food.fat_g * servings)}g`} />
        </div>
      </div>

      <div>
        <label>Servings ({food.serving_description} each)</label>
        <input type="number" step="0.25" min="0.25" value={servings} onChange={(e) => setServings(e.target.value)} />
      </div>

      <div>
        <label>Add to meal</label>
        <select value={mealType} onChange={(e) => setMealType(e.target.value)}>
          {MEALS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
      </div>

      <ErrorBanner message={error} />
      <button className="btn btn-primary btn-block" onClick={handleAdd} disabled={saving}>
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
