import { useEffect, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import PageHeader from "../../components/PageHeader";
import { Loading, ErrorBanner, extractErrorMessage } from "../../components/Status";
import { createTemplate, getTemplate, updateTemplate, addExerciseToTemplate, removeExerciseFromTemplate, updateTemplateExercise, searchExercises } from "../../api/workouts";

export default function TemplateEditor() {
  const { id } = useParams();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();

  const [template, setTemplate] = useState(null);
  const [title, setTitle] = useState("New Template");
  const [kind] = useState(searchParams.get("kind") || "main");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [showSearch, setShowSearch] = useState(false);

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

  async function handleRemoveExercise(exerciseId, exerciseName) {
    if (!window.confirm(`Remove "${exerciseName}" from this routine?`)) return;
    try {
      const updated = await removeExerciseFromTemplate(template.id, exerciseId);
      setTemplate(updated);
    } catch (err) {
      setError(extractErrorMessage(err, "Couldn't remove that exercise."));
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
      navigate("/workouts");
    } catch (err) {
      setError(extractErrorMessage(err, "Couldn't save. Check your connection."));
    } finally {
      setSaving(false);
    }
  }

  function handleBack() {
    // Every field except the title saves immediately on change (add/remove
    // exercise, target sets, weight unit), so leaving never loses those.
    // The title is the one exception -- it's only local state until Save
    // is clicked -- so only warn when there's an actual unsaved rename on
    // an already-persisted template. A never-saved draft has nothing to
    // lose by design (see the draft-mode comment above).
    const hasUnsavedTitle = template.id && title.trim() && title.trim() !== template.title;
    if (hasUnsavedTitle && !window.confirm("Discard the unsaved routine name change?")) {
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
          Generated routines can't be edited directly. Delete it from the dashboard and tap Generate again for a new one.
        </p>
        {template.exercises.map((ex) => (
          <div key={ex.id} className="card" style={{ marginBottom: 10 }}>
            <p style={{ fontWeight: 600 }}>{ex.exercise_name}</p>
            <p style={{ fontSize: 12, color: "var(--text-faint)" }}>
              {ex.category_name} {ex.equipment_name ? `· ${ex.equipment_name}` : ""}
            </p>
            <p style={{ fontSize: 13, marginTop: 6 }}>{ex.target_sets} target sets · {ex.weight_unit}</p>
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="page">
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
                onClick={() => handleRemoveExercise(ex.id, ex.exercise_name)}
              >
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
    </div>
  );
}

function ExerciseSearch({ onAdd, onClose }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (query.trim().length < 2) {
      setResults([]);
      return;
    }
    const t = setTimeout(async () => {
      setLoading(true);
      setError("");
      try {
        const r = await searchExercises(query);
        setResults(r);
      } catch (err) {
        setError("Couldn't search exercises. Has the exercise database been synced yet? Run: python manage.py sync_wger_exercises");
      } finally {
        setLoading(false);
      }
    }, 350);
    return () => clearTimeout(t);
  }, [query]);

  return (
    <div className="page">
      <PageHeader title="Add Exercise" back={false} action={<button className="btn-ghost" style={{ background: "none", border: "none" }} onClick={onClose}>Close</button>} />
      <input autoFocus placeholder="Search for an exercise" value={query} onChange={(e) => setQuery(e.target.value)} />
      {loading && <Loading label="Searching" />}
      <ErrorBanner message={error} />
      {!loading && query.length >= 2 && results.length === 0 && !error && (
        <p style={{ color: "var(--text-faint)", fontSize: 13 }}>No exercises found for "{query}".</p>
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
    </div>
  );
}