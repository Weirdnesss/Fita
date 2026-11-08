import { useEffect, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import PageHeader from "../../components/PageHeader";
import { Loading, ErrorBanner, extractErrorMessage } from "../../components/Status";
import { createTemplate, getTemplate, updateTemplate, addExerciseToTemplate, removeExerciseFromTemplate, updateTemplateExercise, swapTemplateExercise, suggestTemplateExercise } from "../../api/workouts";
import ConfirmDialog from "../../components/ConfirmDialog";
import { useToast } from "../../context/ToastContext";
import Pinned from "../../components/Pinned";
import ExerciseSearch from "./ExerciseSearch";

const MAX_TARGET_SETS = 10;
const MIN_GENERATED_EXERCISES = 1;
const MAX_GENERATED_EXERCISES = 15;

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
    if (newTargetSets < 1 || newTargetSets > MAX_TARGET_SETS) return;
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
        templateId={template.is_generated ? template.id : null}
        onSuggest={
          template.is_generated
            ? async () => {
                const updated = await suggestTemplateExercise(template.id);
                handleExerciseAdded(updated);
                const added = updated.exercises[updated.exercises.length - 1];
                showToast(`Added ${added.exercise_name}`, "success");
              }
            : null
        }
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
    // Generated routines keep their structure (title, set counts, goal-based
    // regeneration), but single exercises can be swapped, removed, or added.
    // Adds are restricted to beginner-safe suggestions from the backend.
    const canRemove = template.exercises.length > MIN_GENERATED_EXERCISES;
    const canAdd = template.exercises.length < MAX_GENERATED_EXERCISES;
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
          You can swap, remove, or add exercises to fit your equipment and schedule.
        </p>
        <ErrorBanner message={error} />
        {template.exercises.map((ex) => (
          <GeneratedExerciseRow
            key={ex.id}
            exercise={ex}
            active={swapTargetId === ex.id}
            swapping={swappingId === ex.id}
            canRemove={canRemove}
            onToggle={() => setSwapTargetId(swapTargetId === ex.id ? null : ex.id)}
            onSwap={(reason) => handleSwapExercise(ex.id, reason)}
            onRemove={() => setPendingRemove({ id: ex.id, name: ex.exercise_name })}
            onWeightUnitChange={(unit) => handleWeightUnitChange(ex.id, unit)}
          />
        ))}
        {canAdd && (
          <Pinned bottom>
            <button className="btn btn-secondary btn-block" onClick={() => setShowSearch(true)}>
              + Add Exercise
            </button>
          </Pinned>
        )}
        <ConfirmDialog
          open={pendingRemove !== null}
          title="Remove exercise"
          message={pendingRemove ? `Remove "${pendingRemove.name}" from this routine?` : ""}
          confirmLabel="Remove"
          onConfirm={confirmRemoveExercise}
          onCancel={() => setPendingRemove(null)}
        />
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
      <Pinned>
      <input
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        placeholder="Enter template title..."
        style={{ fontSize: 18, fontWeight: 600 }}
      />
      </Pinned>
      <ErrorBanner message={error} />

      <div>
        <h3 style={{ marginBottom: 10 }}>Exercises ({template.exercises.length})</h3>
        {template.exercises.length === 0 && (
          <div className="empty-state">
            <p>No exercises added yet</p>
          </div>
        )}
        {template.exercises.map((ex) => (
          <div key={ex.id} className="card card-accent" style={{ marginBottom: 10, "--accent-color": "var(--chili)" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
              <div>
                <p style={{ fontWeight: 600 }}>{ex.exercise_name}</p>
                <p style={{ fontSize: 12, color: "var(--text-faint)" }}>
                  {ex.category_name} {ex.equipment_name ? `· ${ex.equipment_name}` : ""}
                </p>
              </div>
              <button
                className="btn-ghost"
                style={{ fontSize: 12 }}
                onClick={() => setPendingRemove({ id: ex.id, name: ex.exercise_name })}
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
                    disabled={ex.target_sets >= MAX_TARGET_SETS}
                    style={{
                      width: 28,
                      height: 28,
                      borderRadius: 8,
                      border: "1px solid var(--border)",
                      background: "transparent",
                      color: ex.target_sets >= MAX_TARGET_SETS ? "var(--text-faint)" : "var(--text-dim)",
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
                      background: ex.weight_unit === unit ? "var(--chili)" : "transparent",
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
        <Pinned bottom>
          <button className="btn btn-secondary btn-block" onClick={() => setShowSearch(true)}>
            + Add Exercise
          </button>
        </Pinned>
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

function GeneratedExerciseRow({ exercise, active, swapping, canRemove, onToggle, onSwap, onRemove, onWeightUnitChange }) {
  const REASONS = [
    ["too_hard", "Too hard"],
    ["unavailable", "Not available"],
    ["wrong", "Not right for me"],
  ];
  return (
    <div className="card card-accent" style={{ marginBottom: 10, "--accent-color": "var(--chili)" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 8 }}>
        <div>
          <p style={{ fontWeight: 600 }}>{exercise.exercise_name}</p>
          <p style={{ fontSize: 12, color: "var(--text-faint)" }}>
            {exercise.category_name} {exercise.equipment_name ? `· ${exercise.equipment_name}` : ""}
          </p>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <button
            className="btn btn-secondary"
            style={{ padding: "6px 12px", fontSize: 12 }}
            onClick={onToggle}
            disabled={swapping}
          >
            Swap
          </button>
          {canRemove && (
            <button
              className="btn-ghost"
              style={{ fontSize: 12 }}
              onClick={onRemove}
              disabled={swapping}
            >
              Remove
            </button>
          )}
        </div>
      </div>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 8, marginTop: 6 }}>
        <p style={{ fontSize: 13 }}>{exercise.target_sets} target sets</p>
        <div style={{ display: "flex", border: "1px solid var(--border)", borderRadius: 8, overflow: "hidden" }}>
          {["kg", "lb"].map((unit) => (
            <button
              key={unit}
              onClick={() => onWeightUnitChange(unit)}
              aria-pressed={exercise.weight_unit === unit}
              style={{
                padding: "6px 12px",
                fontSize: 12,
                fontWeight: 600,
                border: "none",
                background: exercise.weight_unit === unit ? "var(--chili)" : "transparent",
                color: exercise.weight_unit === unit ? "#fff" : "var(--text-dim)",
              }}
            >
              {unit}
            </button>
          ))}
        </div>
      </div>
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
