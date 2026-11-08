import { useEffect, useRef, useState } from "react";
import PageHeader from "../../components/PageHeader";
import Pinned from "../../components/Pinned";
import { Loading, ErrorBanner, extractErrorMessage } from "../../components/Status";
import { searchExercisesPaged, getExerciseCategories, getTemplateExerciseSuggestions } from "../../api/workouts";

/**
 * Pick an exercise to add. Used by the routine editor and by an active workout.
 * onAdd receives the exercise's wger id and the full search result.
 * `templateId` is set for generated routines, which only get beginner-safe suggestions.
 */
export default function ExerciseSearch({ templateId, onSuggest, onAdd, onClose }) {
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState(null);
  const [categories, setCategories] = useState([]);
  const [results, setResults] = useState([]);
  const [count, setCount] = useState(0);
  const [nextOffset, setNextOffset] = useState(null);
  const [hint, setHint] = useState(null);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [suggesting, setSuggesting] = useState(false);
  const [error, setError] = useState("");

  // Guards against a stale response (from a query/category that's since
  // changed, e.g. fast-switching categories) landing after a newer one
  // and clobbering it. Mirrors nutrition's FoodSearch.
  const requestIdRef = useRef(0);

  useEffect(() => {
    // Generated routines get their categories from the suggestions response.
    if (templateId) return;
    getExerciseCategories().then(setCategories).catch(() => setCategories([]));
  }, [templateId]);

  useEffect(() => {
    const t = setTimeout(async () => {
      const requestId = ++requestIdRef.current;
      setLoading(true);
      setError("");
      try {
        if (templateId) {
          const r = await getTemplateExerciseSuggestions(templateId, query, category);
          if (requestId !== requestIdRef.current) return; // superseded
          setResults(r.results);
          setCount(r.results.length);
          setNextOffset(null);
          setHint(null);
          setCategories(r.categories);
        } else {
          const r = await searchExercisesPaged(query, category, 0);
          if (requestId !== requestIdRef.current) return; // superseded
          setResults(r.results);
          setCount(r.count);
          setNextOffset(r.next_offset);
          setHint(r.hint || null);
        }
      } catch (err) {
        if (requestId !== requestIdRef.current) return;
        setError("Couldn't search exercises. Check your connection and try again.");
      } finally {
        if (requestId === requestIdRef.current) setLoading(false);
      }
    }, 300);
    return () => clearTimeout(t);
  }, [query, category, templateId]);

  async function handleLoadMore() {
    setLoadingMore(true);
    try {
      const r = await searchExercisesPaged(query, category, nextOffset);
      setResults((prev) => [...prev, ...r.results]);
      setNextOffset(r.next_offset);
    } catch (err) {
      setError("Couldn't load more exercises.");
    } finally {
      setLoadingMore(false);
    }
  }

  async function handleSuggest() {
    setSuggesting(true);
    setError("");
    try {
      await onSuggest(); // parent adds the exercise and closes the picker
    } catch (err) {
      setError(extractErrorMessage(err, "Couldn't find an exercise to suggest."));
      setSuggesting(false);
    }
  }

  return (
    <div className="page">
      <PageHeader title="Add Exercise" back onBack={onClose} />
      <Pinned>
      {onSuggest && (
        <button
          className="btn btn-primary btn-block"
          style={{ marginBottom: 12 }}
          onClick={handleSuggest}
          disabled={suggesting}
        >
          {suggesting ? "Finding one..." : "Suggest one for me"}
        </button>
      )}
      
        <input autoFocus placeholder="Search for an exercise" value={query} onChange={(e) => setQuery(e.target.value)} />

        {categories.length > 0 && (
          <div style={{ display: "flex", gap: 6, overflowX: "auto", paddingBottom: 4 }}>
            <CategoryChip active={category === null} label="All" onClick={() => setCategory(null)} />
            {categories.map((c) => (
              <CategoryChip key={c} active={category === c} label={c} onClick={() => setCategory(category === c ? null : c)} />
            ))}
          </div>
        )}
      </Pinned>
      {loading && <Loading label="Searching" />}
      <ErrorBanner message={error} />
      {hint && !loading && (
        <p style={{ color: "var(--text-faint)", fontSize: 13 }}>{hint}</p>
      )}
      {!loading && !hint && results.length === 0 && !error && (
        <p style={{ color: "var(--text-faint)", fontSize: 13 }}>
          {templateId
            ? "No more suggested exercises available for this routine."
            : query || category ? `No exercises found.` : "No exercises available."}
        </p>
      )}
      <div className="resource-results-grid">
        {results.map((ex) => (
          <div
            key={ex.wger_exercise_id}
            className="card card-accent"
            style={{ marginBottom: 8, cursor: "pointer", "--accent-color": "var(--chili)" }}
            onClick={() => onAdd(ex.wger_exercise_id, ex)}
          >
            <p style={{ fontWeight: 600 }}>{ex.name}</p>
            {ex.category && <p style={{ fontSize: 12, color: "var(--text-faint)" }}>{ex.category}</p>}
          </div>
        ))}
      </div>
      {nextOffset !== null && !loading && (
        <button className="btn btn-secondary" style={{ width: "100%" }} onClick={handleLoadMore} disabled={loadingMore}>
          {loadingMore ? "Loading..." : `Load More (${count - results.length} left)`}
        </button>
      )}
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