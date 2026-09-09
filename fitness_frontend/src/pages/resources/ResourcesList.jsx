import { useEffect, useRef, useState } from "react";
import PageHeader from "../../components/PageHeader";
import { Loading, ErrorBanner, EmptyState, extractErrorMessage } from "../../components/Status";
import { listResources } from "../../api/resources";
import { searchExercisesPaged } from "../../api/workouts";
import { searchFoods } from "../../api/nutrition";

const TABS = [
  ["exercises", "Exercises"],
  ["food", "Food"],
  ["articles", "Articles"],
];

const ARTICLE_CATEGORIES = [
  ["workout", "Workout"],
  ["nutrition", "Nutrition"],
  ["general", "General"],
];

// Mirrors nutrition.models.FoodCategory on the backend -- duplicated
// from FoodSearch.jsx since this is a separate read-only browsing
// context (no "add to log" flow, so reusing that page directly didn't fit).
const FOOD_CATEGORIES = [
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

export default function ResourcesList() {
  const [tab, setTab] = useState("exercises");

  return (
    <div className="page">
      <PageHeader title="Resources" subtitle="Exercises, Food & Articles" />

      <div style={{ display: "flex", gap: 6 }}>
        {TABS.map(([value, label]) => (
          <button
            key={value}
            className={tab === value ? "btn btn-primary" : "btn btn-secondary"}
            style={{ flex: 1 }}
            onClick={() => setTab(value)}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === "exercises" && <ExercisesTab />}
      {tab === "food" && <FoodTab />}
      {tab === "articles" && <ArticlesTab />}
    </div>
  );
}

/* ============================================================
   EXERCISES
   ============================================================ */

function ExercisesTab() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [count, setCount] = useState(0);
  const [nextOffset, setNextOffset] = useState(null);
  const [hint, setHint] = useState("");
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState(null);
  const requestIdRef = useRef(0);

  useEffect(() => {
    if (query.trim().length === 0) {
      setResults([]);
      setCount(0);
      setNextOffset(null);
      setHint("");
      return;
    }
    const t = setTimeout(async () => {
      const requestId = ++requestIdRef.current;
      setLoading(true);
      try {
        const r = await searchExercisesPaged(query, null, 0);
        if (requestId !== requestIdRef.current) return;
        setResults(r.results);
        setCount(r.count);
        setNextOffset(r.next_offset);
        setHint(r.hint || "");
      } catch (err) {
        if (requestId !== requestIdRef.current) return;
        setError(extractErrorMessage(err));
      } finally {
        if (requestId === requestIdRef.current) setLoading(false);
      }
    }, 300);
    return () => clearTimeout(t);
  }, [query]);

  async function handleLoadMore() {
    if (nextOffset === null || loadingMore) return;
    const requestId = ++requestIdRef.current;
    setLoadingMore(true);
    try {
      const r = await searchExercisesPaged(query, null, nextOffset);
      if (requestId !== requestIdRef.current) return;
      setResults((prev) => [...prev, ...r.results]);
      setNextOffset(r.next_offset);
    } catch (err) {
      if (requestId !== requestIdRef.current) return;
      setError(extractErrorMessage(err));
    } finally {
      if (requestId === requestIdRef.current) setLoadingMore(false);
    }
  }

  if (selected) {
    return <ExerciseDetail exercise={selected} onBack={() => setSelected(null)} />;
  }

  return (
    <>
      <input autoFocus placeholder="Search exercises (e.g. bench press, squat)" value={query} onChange={(e) => setQuery(e.target.value)} />
      {loading && <Loading />}
      <ErrorBanner message={error} />
      {hint && <p style={{ fontSize: 13, color: "var(--text-faint)" }}>{hint}</p>}
      {!loading && !hint && query.trim().length === 0 && (
        <p style={{ fontSize: 13, color: "var(--text-faint)" }}>Search for an exercise to see how to do it.</p>
      )}
      {!loading && !hint && query.trim().length > 0 && results.length === 0 && (
        <p style={{ fontSize: 13, color: "var(--text-faint)" }}>No results for "{query}".</p>
      )}
      {!loading && results.length > 0 && count > results.length && (
        <p style={{ fontSize: 12, color: "var(--text-faint)" }}>Showing {results.length} of {count}</p>
      )}
      {results.map((ex) => (
        <div key={ex.wger_exercise_id} className="card" style={{ marginBottom: 8, cursor: "pointer" }} onClick={() => setSelected(ex)}>
          <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
            <p style={{ fontWeight: 600 }}>{ex.name}</p>
            {ex.category && <span className="pill pill-neutral" style={{ flexShrink: 0 }}>{ex.category}</span>}
          </div>
          {ex.muscles && <p style={{ fontSize: 12, color: "var(--text-faint)", marginTop: 4 }}>{ex.muscles}</p>}
        </div>
      ))}
      {!loading && nextOffset !== null && (
        <button className="btn btn-secondary btn-block" onClick={handleLoadMore} disabled={loadingMore}>
          {loadingMore ? "Loading..." : `Load More (${count - results.length} left)`}
        </button>
      )}
    </>
  );
}

function ExerciseDetail({ exercise, onBack }) {
  return (
    <>
      <PageHeader
        title={exercise.name}
        subtitle={exercise.category || undefined}
        back={false}
        action={<button className="btn-ghost" style={{ background: "none", border: "none" }} onClick={onBack}>Back to Search</button>}
      />
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
        {exercise.category && <span className="pill pill-chili">{exercise.category}</span>}
        {exercise.equipment && <span className="pill pill-neutral">{exercise.equipment}</span>}
      </div>
      {exercise.muscles && (
        <div className="card">
          <p className="eyebrow" style={{ marginBottom: 6 }}>Muscles Worked</p>
          <p style={{ fontSize: 14 }}>{exercise.muscles}</p>
        </div>
      )}
      <div className="card">
        <p className="eyebrow" style={{ marginBottom: 6 }}>How To</p>
        {exercise.description ? (
          <p style={{ fontSize: 14, lineHeight: 1.6, whiteSpace: "pre-line" }}>{exercise.description}</p>
        ) : (
          <p style={{ fontSize: 13, color: "var(--text-faint)" }}>No description available for this exercise yet.</p>
        )}
      </div>
    </>
  );
}

/* ============================================================
   FOOD
   ============================================================ */

function FoodTab() {
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState(null);
  const [results, setResults] = useState([]);
  const [count, setCount] = useState(0);
  const [nextOffset, setNextOffset] = useState(null);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState(null);
  const requestIdRef = useRef(0);

  useEffect(() => {
    const t = setTimeout(async () => {
      const requestId = ++requestIdRef.current;
      setLoading(true);
      try {
        const r = await searchFoods(query, category, 0);
        if (requestId !== requestIdRef.current) return;
        setResults(r.results);
        setCount(r.count);
        setNextOffset(r.next_offset);
      } catch (err) {
        if (requestId !== requestIdRef.current) return;
        setError(extractErrorMessage(err));
      } finally {
        if (requestId === requestIdRef.current) setLoading(false);
      }
    }, 300);
    return () => clearTimeout(t);
  }, [query, category]);

  async function handleLoadMore() {
    if (nextOffset === null || loadingMore) return;
    const requestId = ++requestIdRef.current;
    setLoadingMore(true);
    try {
      const r = await searchFoods(query, category, nextOffset);
      if (requestId !== requestIdRef.current) return;
      setResults((prev) => [...prev, ...r.results]);
      setNextOffset(r.next_offset);
    } catch (err) {
      if (requestId !== requestIdRef.current) return;
      setError(extractErrorMessage(err));
    } finally {
      if (requestId === requestIdRef.current) setLoadingMore(false);
    }
  }

  if (selected) {
    return <FoodDetail food={selected} onBack={() => setSelected(null)} />;
  }

  return (
    <>
      <input placeholder="Search foods (e.g. adobo, rice)" value={query} onChange={(e) => setQuery(e.target.value)} />
      <div style={{ display: "flex", gap: 6, overflowX: "auto", paddingBottom: 4 }}>
        <CategoryChip active={category === null} label="All" onClick={() => setCategory(null)} />
        {FOOD_CATEGORIES.map(([value, label]) => (
          <CategoryChip key={value} active={category === value} label={label} onClick={() => setCategory(category === value ? null : value)} />
        ))}
      </div>
      {loading && <Loading />}
      <ErrorBanner message={error} />
      {!loading && query.trim().length === 0 && category === null && (
        <p style={{ fontSize: 13, color: "var(--text-faint)" }}>Try "rice", "adobo", or pick a category above.</p>
      )}
      {!loading && results.length === 0 && (query.trim().length > 0 || category !== null) && (
        <p style={{ fontSize: 13, color: "var(--text-faint)" }}>No results{query.trim() && ` for "${query}"`}.</p>
      )}
      {!loading && results.length > 0 && count > results.length && (
        <p style={{ fontSize: 12, color: "var(--text-faint)" }}>Showing {results.length} of {count}</p>
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
              <span className={`pill ${food.is_verified ? "pill-bamboo" : "pill-neutral"}`} style={{ marginTop: 4 }}>
                {food.is_verified ? "PhilFCT" : "Estimated"}
              </span>
            </div>
          </div>
        </div>
      ))}
      {!loading && nextOffset !== null && (
        <button className="btn btn-secondary btn-block" onClick={handleLoadMore} disabled={loadingMore}>
          {loadingMore ? "Loading..." : `Load More (${count - results.length} left)`}
        </button>
      )}
    </>
  );
}

function FoodDetail({ food, onBack }) {
  return (
    <>
      <PageHeader
        title={food.name}
        subtitle={food.local_name || undefined}
        back={false}
        action={<button className="btn-ghost" style={{ background: "none", border: "none" }} onClick={onBack}>Back to Search</button>}
      />
      <span className={`pill ${food.is_verified ? "pill-bamboo" : "pill-neutral"}`}>
        {food.is_verified ? "PhilFCT" : "Estimated"}
      </span>
      <div className="card">
        <p className="eyebrow" style={{ marginBottom: 8 }}>Per {food.serving_description}</p>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 8, textAlign: "center" }}>
          <MacroBox label="Calories" value={Math.round(food.calories)} />
          <MacroBox label="Protein" value={`${Math.round(food.protein_g)}g`} />
          <MacroBox label="Carbs" value={`${Math.round(food.carbs_g)}g`} />
          <MacroBox label="Fat" value={`${Math.round(food.fat_g)}g`} />
        </div>
      </div>
      {(food.fiber_g != null || food.sodium_mg != null) && (
        <div className="card" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {food.fiber_g != null && <DetailRow label="Fiber" value={`${food.fiber_g}g`} />}
          {food.sodium_mg != null && <DetailRow label="Sodium" value={`${food.sodium_mg}mg`} />}
        </div>
      )}
      {food.source && <p style={{ fontSize: 12, color: "var(--text-faint)" }}>Source: {food.source}</p>}
    </>
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

function DetailRow({ label, value }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 14 }}>
      <span style={{ color: "var(--text-dim)" }}>{label}</span>
      <span style={{ fontWeight: 500 }}>{value}</span>
    </div>
  );
}

/* ============================================================
   ARTICLES
   ============================================================ */

function ArticlesTab() {
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState(null);
  const [resources, setResources] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    const t = setTimeout(async () => {
      try {
        const r = await listResources({ category, q: query });
        setResources(r);
      } catch (err) {
        setError(extractErrorMessage(err));
      }
    }, 300);
    return () => clearTimeout(t);
  }, [query, category]);

  return (
    <>
      <input placeholder="Search articles" value={query} onChange={(e) => setQuery(e.target.value)} />
      <div style={{ display: "flex", gap: 6, overflowX: "auto", paddingBottom: 4 }}>
        <CategoryChip active={category === null} label="All" onClick={() => setCategory(null)} />
        {ARTICLE_CATEGORIES.map(([value, label]) => (
          <CategoryChip key={value} active={category === value} label={label} onClick={() => setCategory(category === value ? null : value)} />
        ))}
      </div>
      <ErrorBanner message={error} />
      {resources === null && <Loading />}
      {resources?.length === 0 && (
        <EmptyState title="No articles yet" eyebrow="Nothing here yet -- check back later" />
      )}
      {resources?.map((r) => (
        <a
          key={r.id}
          href={r.url}
          target="_blank"
          rel="noreferrer noopener"
          className="card card-tab"
          style={{ marginBottom: 10, display: "block", textDecoration: "none", color: "inherit" }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 8, marginBottom: 6 }}>
            <p style={{ fontWeight: 600 }}>{r.title}</p>
            <ArticleCategoryPill category={r.category} />
          </div>
          {r.summary && (
            <p style={{ fontSize: 13, color: "var(--text-dim)", marginBottom: 6 }}>{r.summary}</p>
          )}
          {r.source && <p style={{ fontSize: 12, color: "var(--text-faint)" }}>{r.source}</p>}
        </a>
      ))}
    </>
  );
}

function ArticleCategoryPill({ category }) {
  const map = {
    workout: "pill-chili",
    nutrition: "pill-bamboo",
    general: "pill-turmeric",
  };
  const label = ARTICLE_CATEGORIES.find(([v]) => v === category)?.[1] || category;
  return <span className={`pill ${map[category] || "pill-turmeric"}`} style={{ flexShrink: 0 }}>{label}</span>;
}

/* ============================================================
   SHARED
   ============================================================ */

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