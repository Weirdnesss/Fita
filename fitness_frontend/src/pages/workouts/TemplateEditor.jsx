import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import PageHeader from "../../components/PageHeader";
import { Loading, ErrorBanner, extractErrorMessage } from "../../components/Status";
import { createTemplate, getTemplate, updateTemplate, addExerciseToTemplate, removeExerciseFromTemplate, updateTemplateExercise, swapTemplateExercise, searchExercisesPaged, getExerciseCategories } from "../../api/workouts";
import ConfirmDialog from "../../components/ConfirmDialog";
import { useToast } from "../../context/ToastContext";

export default function TemplateEditor() {
  const { id } = useParams();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const showToast = useToast();

  const [template, setTemplate] = useState(null);
  const [title, setTitle] = useState("New Template");
  const [kind] = useState(searchParams.get("kind") || "main");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [showSearch, setShowSearch] = useState(false);
  const [swapTargetId, setSwapTargetId] = useState(null);
  const [swappingId, setSwappingId] = useState(null);
  const [pendingRemove, setPendingRemove] = useState(null); // { id, name } | null
  const [confirmingBack, setConfirmingBack] = useState(false);

  useEffect(() => {
    if (id) {
      getTemplate(id).then((t) => {
        setTemplate(t);
        setTitle(t.title);
      }).catch((err) => setError(extractErrorMessage(err)));
    } else {
      // Draft mode: nothing is persisted yet. The row is only created
      // once the user actually adds an exercise or hits Save, so
      // navigating away from an untouched "new template" leaves no
      // orphaned rows behind.
      setTemplate({ id: null, title: "New Template", kind, exercises: [] });
    }
  }, [id]);

  // Creates the template on the server the first time it's needed
  // (adding an exercise, or hitting Save), and reuses the existing id
  // on every call after that. Returns the persisted template. Falls
  // back to "New Template" if the title is blank/whitespace-only --
  // an empty title shouldn't block the core action of adding an
  // exercise; the user can always rename it afterward.
  async function ensureTemplatePersisted() {
    if (template.id) return template;
    const effectiveTitle = title.trim() || "New Template";
    const created = await createTemplate({ title: effectiveTitle, kind });
    setTemplate(created);
    setTitle(created.title);
    navigate(`/workouts/templates/${created.id}`, { replace: true });
    return created;
  }

  async function handleExerciseAdded(updatedTemplate) {
    setTemplate(updatedTemplate);
    setShowSearch(false);
  }

  async function confirmRemoveExercise() {
    const { id: exerciseId, name } = pendingRemove;
    setPendingRemove(null);
    try {
      const updated = await removeExerciseFromTemplate(template.id, exerciseId);
      setTemplate(updated);
      showToast(`Removed ${name}`, "success");
    } catch (err) {
      showToast(extractErrorMessage(err, "Couldn't remove that exercise."), "error");
    }
  }

  async function handleTargetSetsChange(exerciseId, newTargetSets) {
    if (newTargetSets < 1) return;
    // Optimistic update so the stepper feels instant.
    setTemplate((prev) => ({
      ...prev,
      exercises: prev.exercises.map((ex) =>
        ex.id === exerciseId ? { ...ex, target_sets: newTargetSets } : ex
      ),
    }));
    try {
      await updateTemplateExercise(template.id, exerciseId, { targetSets: newTargetSets });
    } catch (err) {
      setError(extractErrorMessage(err, "Couldn't update target sets."));
      // Roll back on failure by re-fetching the template's real state.
      getTemplate(template.id).then(setTemplate).catch(() => {});
    }
  }

  async function handleWeightUnitChange(exerciseId, newUnit) {
    setTemplate((prev) => ({
      ...prev,
      exercises: prev.exercises.map((ex) =>
        ex.id === exerciseId ? { ...ex, weight_unit: newUnit } : ex
      ),
    }));
    try {
      await updateTemplateExercise(template.id, exerciseId, { weightUnit: newUnit });
    } catch (err) {
      setError(extractErrorMessage(err, "Couldn't update weight unit."));
      getTemplate(template.id).then(setTemplate).catch(() => {});
    }
  }

  async function handleSwapExercise(exerciseId, reason) {
    setSwappingId(exerciseId);
    setError("");
    try {
      const updated = await swapTemplateExercise(template.id, exerciseId, reason);
      setTemplate(updated);
      showToast("Exercise swapped", "success");
      setSwapTargetId(null);
    } catch (err) {
      setError(extractErrorMessage(err, "Couldn't find a replacement exercise."));
    } finally {
      setSwappingId(null);
    }
  }

  async function handleSave() {
    setSaving(true);
    setError("");
    const effectiveTitle = title.trim() || "New Template";
    try {
      if (template.id) {
        await updateTemplate(template.id, { title: effectiveTitle });
      } else {
        await createTemplate({ title: effectiveTitle, kind });
      }
      showToast("Routine saved", "success");
      navigate("/workouts");
    } catch (err) {
      setError(extractErrorMessage(err, "Couldn't save. Check your connection."));
    } finally {
      setSaving(false);
    }
  }

  function handleBack() {
    // Same reasoning as before: only the title can be unsaved when
    // leaving, since every other field saves immediately on change.
    const hasUnsavedTitle = template.id && title.trim() && title.trim() !== template.title;
    if (hasUnsavedTitle) {
      setConfirmingBack(true);
      return;
    }
    navigate("/workouts");
  }

  if (!template) {
    return (
      <div className="page">
        <PageHeader title="Loading" back backTo="/workouts" />
        <ErrorBanner message={error} />
        {!error && <Loading />}
      </div>
    );
  }

  if (showSearch) {
    return (
      <ExerciseSearch
        onAdd={async (wgerExerciseId) => {
          try {
            const persisted = await ensureTemplatePersisted();
            const updated = await addExerciseToTemplate(persisted.id, { wgerExerciseId });
            handleExerciseAdded(updated);
            showToast("Exercise added", "success");
          } catch (err) {
            setError(extractErrorMessage(err, "Couldn't add that exercise. Check your connection."));
          }
        }}
        onClose={() => setShowSearch(false)}
      />
    );
  }

  if (template.is_generated) {
    // Generated routines are regenerated in place from the Workouts
    // dashboard, not edited here -- the dashboard already hides the
    // Edit button for these, but this read-only view is the backstop
    // if someone lands here directly (a bookmarked/typed URL, back
    // button after deletion, etc.), matching the same guard the
    // backend enforces on every mutation for a generated template.
    // Swapping a single exercise is the one exception: it's allowed
    // here even though nothing else is, since it doesn't touch the
    // weekly Generate cooldown.
    return (
      <div className="page">
        <PageHeader
          title={template.title}
          back
          backTo="/workouts"
          action={
            <button className="btn btn-primary" style={{ padding: "8px 14px", fontSize: 13 }} onClick={() => navigate(`/workouts/templates/${template.id}/start`)}>
              Start
            </button>
          }
        />
        <p style={{ fontSize: 13, color: "var(--text-faint)", marginBottom: 16 }}>
          Generated routines can't be edited directly, but you can swap out a single exercise below if it's too hard, unavailable, or not right for you.
        </p>
        <ErrorBanner message={error} />
        {template.exercises.map((ex) => (
          <GeneratedExerciseRow
            key={ex.id}
            exercise={ex}
            active={swapTargetId === ex.id}
            swapping={swappingId === ex.id}
            onToggle={() => setSwapTargetId(swapTargetId === ex.id ? null : ex.id)}
            onSwap={(reason) => handleSwapExercise(ex.id, reason)}
          />
        ))}
      </div>
    );
  }

  return (
    <div className="page template-editor">
      <PageHeader
        title="Edit Routine"
        back
        onBack={handleBack}
        action={
          <div style={{ display: "flex", gap: 8 }}>
            <button className="btn btn-secondary" style={{ padding: "8px 14px", fontSize: 13 }} onClick={handleSave} disabled={saving}>
              {saving ? "Saving..." : "Save"}
            </button>
            {template.exercises.length > 0 && (
              <button className="btn btn-primary" style={{ padding: "8px 14px", fontSize: 13 }} onClick={() => navigate(`/workouts/templates/${template.id}/start`)}>
                Start
              </button>
            )}
          </div>
        }
      />
      <input
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        placeholder="Enter template title..."
        style={{ fontSize: 18, fontWeight: 600 }}
      />
      <ErrorBanner message={error} />

      <div>
        <h3 style={{ marginBottom: 10 }}>Exercises ({template.exercises.length})</h3>
        {template.exercises.length === 0 && (
          <div className="empty-state">
            <p>No exercises added yet</p>
          </div>
        )}
        {template.exercises.map((ex) => (
          <div key={ex.id} className="card" style={{ marginBottom: 10 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
              <div>
                <p style={{ fontWeight: 600 }}>{ex.exercise_name}</p>
                <p style={{ fontSize: 12, color: "var(--text-faint)" }}>
                  {ex.category_name} {ex.equipment_name ? `· ${ex.equipment_name}` : ""}
                </p>
              </div>
              <button
                className="btn-ghost"
                style={{ background: "none", border: "none", color: "var(--chili)", fontSize: 12 }}
                onClick={() => setPendingRemove({ id: ex.id, name: ex.exercise_name })}              >
                Remove
              </button>
            </div>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10, marginTop: 10, flexWrap: "wrap" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <span style={{ fontSize: 13, color: "var(--text-dim)" }}>Target sets</span>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <button
                    aria-label="Decrease target sets"
                    onClick={() => handleTargetSetsChange(ex.id, ex.target_sets - 1)}
                    disabled={ex.target_sets <= 1}
                    style={{
                      width: 28,
                      height: 28,
                      borderRadius: 8,
                      border: "1px solid var(--border)",
                      background: "transparent",
                      color: ex.target_sets <= 1 ? "var(--text-faint)" : "var(--text-dim)",
                    }}
                  >
                    −
                  </button>
                  <span className="stat" style={{ fontSize: 15, minWidth: 18, textAlign: "center" }}>
                    {ex.target_sets}
                  </span>
                  <button
                    aria-label="Increase target sets"
                    onClick={() => handleTargetSetsChange(ex.id, ex.target_sets + 1)}
                    style={{
                      width: 28,
                      height: 28,
                      borderRadius: 8,
                      border: "1px solid var(--border)",
                      background: "transparent",
                      color: "var(--text-dim)",
                    }}
                  >
                    +
                  </button>
                </div>
              </div>

              <div style={{ display: "flex", border: "1px solid var(--border)", borderRadius: 8, overflow: "hidden" }}>
                {["kg", "lb"].map((unit) => (
                  <button
                    key={unit}
                    onClick={() => handleWeightUnitChange(ex.id, unit)}
                    aria-pressed={ex.weight_unit === unit}
                    style={{
                      padding: "6px 12px",
                      fontSize: 12,
                      fontWeight: 600,
                      border: "none",
                      background: ex.weight_unit === unit ? "var(--bamboo)" : "transparent",
                      color: ex.weight_unit === unit ? "#fff" : "var(--text-dim)",
                    }}
                  >
                    {unit}
                  </button>
                ))}
              </div>
            </div>
          </div>
        ))}
        <button className="btn btn-secondary btn-block" onClick={() => setShowSearch(true)}>
          + Add Exercise
        </button>
      </div>

      <ConfirmDialog
        open={pendingRemove !== null}
        title="Remove exercise"
        message={pendingRemove ? `Remove "${pendingRemove.name}" from this routine?` : ""}
        confirmLabel="Remove"
        onConfirm={confirmRemoveExercise}
        onCancel={() => setPendingRemove(null)}
      />
      <ConfirmDialog
        open={confirmingBack}
        title="Discard changes"
        message="Discard the unsaved routine name change?"
        confirmLabel="Discard"
        onConfirm={() => { setConfirmingBack(false); navigate("/workouts"); }}
        onCancel={() => setConfirmingBack(false)}
      />
    </div>
  );
}

function GeneratedExerciseRow({ exercise, active, swapping, onToggle, onSwap }) {
  const REASONS = [
    ["too_hard", "Too hard"],
    ["unavailable", "Not available"],
    ["wrong", "Not right for me"],
  ];
  return (
    <div className="card" style={{ marginBottom: 10 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <p style={{ fontWeight: 600 }}>{exercise.exercise_name}</p>
          <p style={{ fontSize: 12, color: "var(--text-faint)" }}>
            {exercise.category_name} {exercise.equipment_name ? `· ${exercise.equipment_name}` : ""}
          </p>
        </div>
        <button
          className="btn-ghost"
          style={{ background: "none", border: "1px solid var(--border)", fontSize: 12, padding: "6px 12px", borderRadius: "var(--radius)" }}
          onClick={onToggle}
          disabled={swapping}
        >
          Swap
        </button>
      </div>
      <p style={{ fontSize: 13, marginTop: 6 }}>{exercise.target_sets} target sets · {exercise.weight_unit}</p>
      {active && (
        <div style={{ display: "flex", gap: 8, marginTop: 10, flexWrap: "wrap" }}>
          {REASONS.map(([value, label]) => (
            <button
              key={value}
              className="btn btn-secondary"
              style={{ padding: "6px 12px", fontSize: 12 }}
              onClick={() => onSwap(value)}
              disabled={swapping}
            >
              {swapping ? "Swapping..." : label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function ExerciseSearch({ onAdd, onClose }) {
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState(null);
  const [categories, setCategories] = useState([]);
  const [results, setResults] = useState([]);
  const [count, setCount] = useState(0);
  const [nextOffset, setNextOffset] = useState(null);
  const [hint, setHint] = useState(null);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState("");

  // Guards against a stale response (from a query/category that's since
  // changed, e.g. fast-switching categories) landing after a newer one
  // and clobbering it. Mirrors nutrition's FoodSearch.
  const requestIdRef = useRef(0);

  useEffect(() => {
    getExerciseCategories().then(setCategories).catch(() => setCategories([]));
  }, []);

  useEffect(() => {
    const t = setTimeout(async () => {
      const requestId = ++requestIdRef.current;
      setLoading(true);
      setError("");
      try {
        const r = await searchExercisesPaged(query, category, 0);
        if (requestId !== requestIdRef.current) return; // superseded
        setResults(r.results);
        setCount(r.count);
        setNextOffset(r.next_offset);
        setHint(r.hint || null);
      } catch (err) {
        if (requestId !== requestIdRef.current) return;
        setError("Couldn't search exercises. Check your connection and try again.");
      } finally {
        if (requestId === requestIdRef.current) setLoading(false);
      }
    }, 300);
    return () => clearTimeout(t);
  }, [query, category]);

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

  return (
    <div className="page">
      <PageHeader title="Add Exercise" back={false} action={<button className="btn-ghost" style={{ background: "none", border: "none" }} onClick={onClose}>Close</button>} />
      <input autoFocus placeholder="Search for an exercise" value={query} onChange={(e) => setQuery(e.target.value)} />

      {categories.length > 0 && (
        <div style={{ display: "flex", gap: 6, overflowX: "auto", paddingBottom: 4 }}>
          <CategoryChip active={category === null} label="All" onClick={() => setCategory(null)} />
          {categories.map((c) => (
            <CategoryChip key={c} active={category === c} label={c} onClick={() => setCategory(category === c ? null : c)} />
          ))}
        </div>
      )}

      {loading && <Loading label="Searching" />}
      <ErrorBanner message={error} />
      {hint && !loading && (
        <p style={{ color: "var(--text-faint)", fontSize: 13 }}>{hint}</p>
      )}
      {!loading && !hint && results.length === 0 && !error && (
        <p style={{ color: "var(--text-faint)", fontSize: 13 }}>
          {query || category ? `No exercises found.` : "No exercises available."}
        </p>
      )}
      {results.map((ex) => (
        <div
          key={ex.wger_exercise_id}
          className="card"
          style={{ marginBottom: 8, cursor: "pointer" }}
          onClick={() => onAdd(ex.wger_exercise_id)}
        >
          <p style={{ fontWeight: 600 }}>{ex.name}</p>
          {ex.category && <p style={{ fontSize: 12, color: "var(--text-faint)" }}>{ex.category}</p>}
        </div>
      ))}
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