import { useEffect, useState, useRef } from "react";
import { useNavigate, useParams } from "react-router-dom";
import PageHeader from "../../components/PageHeader";
import { Loading, ErrorBanner, extractErrorMessage } from "../../components/Status";
import { getTemplate, finishWorkout, lbToKg } from "../../api/workouts";

function sessionKey(templateId) {
  return `active_workout_${templateId}`;
}

export default function ActiveWorkout() {
  const { id } = useParams();
  const navigate = useNavigate();
  const startedAtRef = useRef(null);

  const [template, setTemplate] = useState(null);
  const [logs, setLogs] = useState({}); // exerciseId -> [{weight, reps, done}]
  const [note, setNote] = useState("");
  const [error, setError] = useState("");
  const [finishing, setFinishing] = useState(false);

  useEffect(() => {
    getTemplate(id)
      .then((t) => {
        setTemplate(t);

        let saved = null;
        try {
          const raw = sessionStorage.getItem(sessionKey(id));
          if (raw) saved = JSON.parse(raw);
        } catch {
          saved = null; // Corrupt/unreadable session data -- ignore.
        }

        // Merge with any saved session instead of an all-or-nothing
        // restore: keep logged sets for exercises that still exist on
        // the template, and initialize fresh rows for any exercise that
        // was added since the session started. This way editing the
        // template mid-workout (e.g. from another tab or after coming
        // back later) doesn't wipe sets already logged for exercises
        // that are still there.
        const merged = {};
        t.exercises.forEach((ex) => {
          merged[ex.id] = saved?.logs?.[ex.id]
            ? saved.logs[ex.id]
            : Array.from({ length: ex.target_sets }, () => ({ weight: "", reps: "", done: false }));
        });
        setLogs(merged);
        setNote(saved?.note || "");
        startedAtRef.current = saved?.startedAt || new Date().toISOString();
      })
      .catch((err) => {
        setError(extractErrorMessage(err));
        // The template is gone (deleted, or never existed) -- any saved
        // session for it can never be resumed, so drop it rather than
        // leaving a dead entry in sessionStorage.
        try {
          sessionStorage.removeItem(sessionKey(id));
        } catch {
          // ignore
        }
      });
  }, [id]);

  // Snapshot to sessionStorage on every change to logs or note, so a
  // refresh, a backgrounded/locked phone, or navigating elsewhere and
  // back doesn't lose logged sets (or the note) mid-workout.
  useEffect(() => {
    if (!template || !startedAtRef.current) return;
    try {
      sessionStorage.setItem(
        sessionKey(id),
        JSON.stringify({ startedAt: startedAtRef.current, logs, note })
      );
    } catch {
      // Storage full/unavailable -- non-fatal, just skip persisting this tick.
    }
  }, [logs, note, template, id]);

  function updateSet(exId, setIndex, field, value) {
    setLogs((prev) => {
      const next = { ...prev };
      next[exId] = [...next[exId]];
      next[exId][setIndex] = { ...next[exId][setIndex], [field]: value };
      return next;
    });
  }

  function toggleDone(exId, setIndex) {
    setLogs((prev) => {
      const next = { ...prev };
      next[exId] = [...next[exId]];
      next[exId][setIndex] = { ...next[exId][setIndex], done: !next[exId][setIndex].done };
      return next;
    });
  }

  function addSet(exId) {
    setLogs((prev) => ({
      ...prev,
      [exId]: [...prev[exId], { weight: "", reps: "", done: false }],
    }));
  }

  function removeSet(exId, setIndex) {
    const set = logs[exId][setIndex];
    const hasData = set.done || set.weight !== "" || set.reps !== "";
    if (hasData && !window.confirm("Remove this set? Logged data will be lost.")) {
      return;
    }
    setLogs((prev) => ({
      ...prev,
      [exId]: prev[exId].filter((_, i) => i !== setIndex),
    }));
  }

  function handleCancel() {
    const hasProgress = Object.values(logs).some((sets) => sets.some((s) => s.done));
    if (hasProgress && !window.confirm("Discard this workout? Logged sets will be lost.")) {
      return;
    }
    sessionStorage.removeItem(sessionKey(id));
    navigate("/workouts");
  }

  async function handleFinish() {
    setError("");

    const exercises = template.exercises
      .map((ex) => ({
        exercise_name: ex.exercise_name,
        weight_unit: ex.weight_unit,
        // Values are typed in the exercise's own unit (kg or lb), but
        // storage is always kg for volume math and cross-unit display
        // -- convert lb entries here. display_weight also keeps the
        // exact number the user typed, so re-viewing history in the
        // same unit shows precisely that value instead of a converted
        // value that's picked up a tiny rounding error from the
        // lb<->kg round trip.
        // Sets are also filtered for valid, in-range numbers here --
        // the number inputs' min= attributes don't actually stop
        // someone from typing a negative value, and letting a bad
        // value reach the backend means the whole Finish request gets
        // rejected with a deeply nested validation error that's not
        // worth trying to surface nicely; simpler to just never send it.
        sets_data: logs[ex.id]
          .filter((s) => s.done && s.weight !== "" && s.reps !== "")
          .filter((s) => Number(s.weight) >= 0 && Number.isInteger(Number(s.reps)) && Number(s.reps) >= 1)
          .map((s) => ({
            weight: ex.weight_unit === "lb" ? lbToKg(Number(s.weight)) : Number(s.weight),
            display_weight: Number(s.weight),
            reps: Number(s.reps),
          })),
      }))
      // Drop exercises with nothing logged -- an exercise that was on
      // the routine but never actually checked off any sets shouldn't
      // be saved.
      .filter((ex) => ex.sets_data.length > 0);

    if (exercises.length === 0) {
      setError("Log at least one set before finishing the workout.");
      return;
    }

    setFinishing(true);
    try {
      await finishWorkout({
        templateTitle: template.title,
        startedAt: startedAtRef.current,
        exercises,
        note: note.trim(),
      });
      sessionStorage.removeItem(sessionKey(id));
      navigate("/workouts");
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setFinishing(false);
    }
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

  return (
    <div className="page">
      <PageHeader
        title={template.title}
        back
        backTo="/workouts"
        action={
          <div style={{ display: "flex", gap: 8 }}>
            <button className="btn-ghost" style={{ padding: "8px 14px", fontSize: 13, background: "none", border: "1px solid var(--border)", color: "var(--text-dim)" }} onClick={handleCancel} disabled={finishing}>
              Cancel
            </button>
            <button className="btn btn-primary" style={{ padding: "8px 14px", fontSize: 13 }} onClick={handleFinish} disabled={finishing}>
              {finishing ? "Saving..." : "Finish Workout"}
            </button>
          </div>
        }
      />
      <ErrorBanner message={error} />

      {template.exercises.map((ex) => (
        <div key={ex.id} className="card">
          <p style={{ fontWeight: 600, marginBottom: 2 }}>{ex.exercise_name}</p>
          <p style={{ fontSize: 12, color: "var(--text-faint)", marginBottom: 12 }}>{ex.category_name}</p>

          <div style={{ display: "grid", gridTemplateColumns: "24px 1fr 1fr 32px 24px", gap: 8, fontSize: 11, color: "var(--text-faint)", marginBottom: 6 }}>
            <span>#</span>
            <span>Weight ({ex.weight_unit})</span>
            <span>Reps</span>
            <span></span>
            <span></span>
          </div>

          {logs[ex.id]?.map((set, i) => (
            <div key={i} style={{ display: "grid", gridTemplateColumns: "24px 1fr 1fr 32px 24px", gap: 8, alignItems: "center", marginBottom: 8 }}>
              <span className="stat" style={{ fontSize: 13, color: "var(--text-dim)" }}>{i + 1}</span>
              <input type="number" min="0" step="any" value={set.weight} onChange={(e) => updateSet(ex.id, i, "weight", e.target.value)} placeholder="0" style={{ padding: "8px 10px" }} />
              <input type="number" min="1" step="1" value={set.reps} onChange={(e) => updateSet(ex.id, i, "reps", e.target.value)} placeholder="0" style={{ padding: "8px 10px" }} />
              <button
                onClick={() => toggleDone(ex.id, i)}
                aria-label="Mark set done"
                style={{
                  width: 32,
                  height: 32,
                  borderRadius: 8,
                  border: "1px solid var(--border)",
                  background: set.done ? "var(--bamboo)" : "transparent",
                  color: set.done ? "#fff" : "var(--text-faint)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                }}
              >
                ✓
              </button>
              <button
                onClick={() => removeSet(ex.id, i)}
                aria-label="Remove set"
                disabled={logs[ex.id].length <= 1}
                style={{
                  width: 24,
                  height: 24,
                  border: "none",
                  background: "none",
                  color: logs[ex.id].length <= 1 ? "var(--text-faint)" : "var(--chili)",
                  fontSize: 16,
                  lineHeight: 1,
                }}
              >
                ×
              </button>
            </div>
          ))}

          <button
            className="btn-ghost"
            onClick={() => addSet(ex.id)}
            style={{
              width: "100%",
              padding: "8px",
              marginTop: 4,
              border: "1px dashed var(--border)",
              borderRadius: 8,
              background: "none",
              color: "var(--text-dim)",
              fontSize: 13,
            }}
          >
            + Add Set
          </button>
        </div>
      ))}

      <div className="card">
        <label htmlFor="workout-note" style={{ fontSize: 13, fontWeight: 600, display: "block", marginBottom: 8 }}>
          Note <span style={{ fontWeight: 400, color: "var(--text-faint)" }}>(optional)</span>
        </label>
        <textarea
          id="workout-note"
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="How did this session feel?"
          maxLength={1000}
          rows={3}
          style={{ width: "100%", padding: "10px 12px", resize: "vertical", fontFamily: "inherit", fontSize: 14 }}
        />
      </div>
    </div>
  );
}