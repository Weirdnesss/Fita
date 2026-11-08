import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Loading, ErrorBanner, extractErrorMessage } from "../../components/Status";
import { getTemplate } from "../../api/workouts";

// A bottom sheet on phones; a centered, narrower dialog on wide screens.
const SHEET_CSS = `
.start-sheet-backdrop { position: fixed; inset: 0; z-index: 50; background: rgba(0, 0, 0, 0.6); display: flex; align-items: flex-end; justify-content: center; }
.start-sheet { width: 100%; max-width: var(--max-width); max-height: 85vh; display: flex; flex-direction: column; background: var(--bg-raised);
  border-top-left-radius: 18px; border-top-right-radius: 18px; padding: 16px 16px calc(16px + env(safe-area-inset-bottom, 0px)); box-shadow: 0 -8px 32px rgba(0, 0, 0, 0.5); }
@media (min-width: 768px) {
  .start-sheet-backdrop { align-items: center; }
  .start-sheet { max-width: 440px; max-height: 70vh; border-radius: 18px; padding-bottom: 16px; box-shadow: 0 12px 40px rgba(0, 0, 0, 0.5); }
}
`;

const TYPE_LABELS = { weight_reps: "Weight & reps", reps: "Reps only", time: "Time" };

/**
 * Bottom sheet shown when you tap Start Workout: a look at what's in the routine
 * before the clock starts. `routine` is { id, title } or null (closed).
 */
// Start replaces the sheet's history entry, so Back from the workout skips the sheet.
export default function WorkoutPreviewSheet({ routine, onClose }) {
  const navigate = useNavigate();
  const [template, setTemplate] = useState(null);
  const [error, setError] = useState("");
  const id = routine?.id;

  useEffect(() => {
    if (id == null) return;
    let cancelled = false;
    setTemplate(null);
    setError("");
    getTemplate(id)
      .then((t) => !cancelled && setTemplate(t))
      .catch((err) => !cancelled && setError(extractErrorMessage(err)));
    return () => {
      cancelled = true;
    };
  }, [id]);

  useEffect(() => {
    if (id == null) return;
    const onKey = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [id, onClose]);

  if (!routine) return null;

  const exercises = template?.exercises || [];
  const totalSets = exercises.reduce((n, ex) => n + (ex.target_sets || 0), 0);
  const canStart = template && exercises.length > 0;

  return (
    <div className="start-sheet-backdrop" onClick={onClose}>
      <style>{SHEET_CSS}</style>
      <div
        className="start-sheet"
        role="dialog"
        aria-modal="true"
        aria-label={`Start ${routine.title}`}
        onClick={(e) => e.stopPropagation()}
      >
        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 12, marginBottom: 12 }}>
          <div style={{ minWidth: 0 }}>
            <h2 style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{routine.title}</h2>
            {template && (
              <p style={{ fontSize: 13, color: "var(--text-dim)" }}>
                {exercises.length} {exercises.length === 1 ? "exercise" : "exercises"} · {totalSets} sets
              </p>
            )}
          </div>
          <button
            onClick={onClose}
            aria-label="Close"
            style={{ background: "none", border: "none", color: "var(--text)", padding: 4, display: "flex" }}
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <path d="M6 6l12 12M18 6L6 18" />
            </svg>
          </button>
        </div>

        <div style={{ overflowY: "auto", flex: 1, minHeight: 0 }}>
          <ErrorBanner message={error} />
          {!template && !error && <Loading />}
          {template && exercises.length === 0 && (
            <p style={{ color: "var(--text-dim)", padding: "8px 0" }}>This routine has no exercises yet. Add some with Edit first.</p>
          )}
          {exercises.map((ex, i) => (
            <div
              key={ex.id}
              style={{ display: "flex", alignItems: "center", gap: 12, padding: "10px 0", borderTop: i ? "1px solid var(--border)" : "none" }}
            >
              <span className="stat" style={{ color: "var(--text-faint)", width: 20, flexShrink: 0 }}>{i + 1}</span>
              <div style={{ minWidth: 0, flex: 1 }}>
                <p style={{ fontWeight: 600 }}>{ex.exercise_name}</p>
                <p style={{ fontSize: 12, color: "var(--text-faint)" }}>
                  {[ex.category_name, TYPE_LABELS[ex.input_type || "weight_reps"]].filter(Boolean).join(" · ")}
                </p>
              </div>
              <span className="stat" style={{ flexShrink: 0 }}>{ex.target_sets} {ex.target_sets === 1 ? "set" : "sets"}</span>
            </div>
          ))}
        </div>

        <button
          className="btn btn-primary"
          style={{ width: "100%", marginTop: 12 }}
          disabled={!canStart}
          onClick={() => navigate(`/workouts/templates/${id}/start`, { replace: true })}
        >
          Start Workout
        </button>
      </div>
    </div>
  );
}
