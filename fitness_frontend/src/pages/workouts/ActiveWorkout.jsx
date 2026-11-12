import { useEffect, useState, useRef } from "react";
import { useNavigate, useParams } from "react-router-dom";
import PageHeader from "../../components/PageHeader";
import { Loading, ErrorBanner, extractErrorMessage } from "../../components/Status";
import { getTemplate, finishWorkout, updateTemplateExercise, addExerciseToTemplate, lbToKg } from "../../api/workouts";
import ConfirmDialog from "../../components/ConfirmDialog";
import UnitToggle from "../../components/UnitToggle";
import { useToast } from "../../context/ToastContext";
import RestTimer from "../../components/RestTimer";
import { useSharedRestTimer } from "../../context/RestTimerContext";
import { buildSummary } from "../../lib/workoutSummary";
import ExerciseSearch from "./ExerciseSearch";
import { getActiveWorkout, setActiveWorkout, clearActiveWorkout, formatElapsed, workoutSessionKey } from "../../lib/activeWorkout";

const sessionKey = workoutSessionKey;

// Derived from lbToKg itself (rather than a separate hardcoded constant)
// so both conversion directions always agree with whatever factor
// api/workouts.lbToKg actually uses.
const KG_PER_LB = lbToKg(1);

function convertWeight(value, fromUnit, toUnit) {
  if (fromUnit === toUnit) return value;
  const converted = fromUnit === "lb" ? lbToKg(value) : value / KG_PER_LB;
  return Math.round(converted * 10) / 10;
}

// How each exercise is logged. Sets saved before this existed have no
// `seconds` key, hence the `?? ""` reads below.
const INPUT_TYPES = [
  ["weight_reps", "Weight & reps"],
  ["reps", "Reps only"],
  ["time", "Time"],
];
const emptySet = () => ({ weight: "", reps: "", seconds: "", done: false });
const setHasData = (s) => s.done || s.weight !== "" || s.reps !== "" || (s.seconds ?? "") !== "";
const validReps = (s) => s.reps !== "" && Number.isInteger(Number(s.reps)) && Number(s.reps) >= 1;
const validSeconds = (s) =>
  (s.seconds ?? "") !== "" && Number.isInteger(Number(s.seconds)) && Number(s.seconds) >= 1 && Number(s.seconds) <= 7200;
// Exercises added during a workout get an id starting with "x-", so they can never clash with a
// routine exercise's numeric id. They live only in this workout's saved state, not on the routine.
const isExtraId = (id) => String(id).startsWith("x-");
const gridCols = (type) => (type === "weight_reps" ? "24px 1fr 1fr 32px 24px" : "24px 1fr 32px 24px");

export default function ActiveWorkout() {
  const { id } = useParams();
  const navigate = useNavigate();
  const startedAtRef = useRef(null);
  const showToast = useToast();

  const [template, setTemplate] = useState(null);
  const [logs, setLogs] = useState({}); // exerciseId -> [{weight, reps, seconds, done}]
  // exerciseId -> "kg" | "lb". Per-exercise so switching one exercise's
  // input unit mid-workout doesn't affect any other exercise's rows.
  const [weightUnits, setWeightUnits] = useState({});
  // exerciseId -> "weight_reps" | "reps" | "time". Switching only changes which
  // fields show and get saved; values typed in hidden fields are kept in
  // case the user switches back.
  const [inputTypes, setInputTypes] = useState({});
  const [note, setNote] = useState("");
  const [error, setError] = useState("");
  const [finishing, setFinishing] = useState(false);
  const [pendingRemoveSet, setPendingRemoveSet] = useState(null); // { exId, setIndex, exerciseName } | null
  const [confirmingCancel, setConfirmingCancel] = useState(false);
  const [finishWarning, setFinishWarning] = useState(null); // { unchecked, skipped } | null
  const [extras, setExtras] = useState([]); // exercises added during this workout (not saved to the routine)
  const [showSearch, setShowSearch] = useState(false);
  const [pendingRemoveExtra, setPendingRemoveExtra] = useState(null); // an extra exercise | null
  const [elapsed, setElapsed] = useState(0); // seconds since startedAtRef.current
  const restTimer = useSharedRestTimer(); // one timer for the whole app, so it keeps running while minimized
  const allExercises = template ? [...template.exercises, ...extras] : [];

  useEffect(() => {
    // One workout at a time: if a different one is in progress, go back to it instead.
    const active = getActiveWorkout();
    if (active && String(active.templateId) !== String(id)) {
      showToast(`Finish or discard "${active.title}" before starting another workout`, "error");
      navigate(`/workouts/templates/${active.templateId}/start`, { replace: true });
      return;
    }

    getTemplate(id)
      .then((t) => {
        setTemplate(t);

        let saved = null;
        try {
          const raw = localStorage.getItem(sessionKey(id));
          if (raw) saved = JSON.parse(raw);
        } catch {
          saved = null; // Corrupt/unreadable session data -- ignore.
        }

        // Merge with any saved session instead of an all-or-nothing
        // restore: keep logged sets for exercises that still exist on
        // the template, and initialize fresh rows for any exercise that
        // was added since the session started.
        const merged = {};
        const mergedUnits = {};
        const mergedTypes = {};
        t.exercises.forEach((ex) => {
          merged[ex.id] = saved?.logs?.[ex.id]
            ? saved.logs[ex.id]
            : Array.from({ length: ex.target_sets }, emptySet);
          // Resume whatever unit/type was chosen mid-session, falling back
          // to the template's own values for this exercise otherwise.
          mergedUnits[ex.id] = saved?.weightUnits?.[ex.id] || ex.weight_unit;
          mergedTypes[ex.id] = saved?.inputTypes?.[ex.id] || ex.input_type || "weight_reps";
        });

        // Exercises added mid-workout aren't on the routine, so they come back from the saved session.
        const savedExtras = Array.isArray(saved?.extras) ? saved.extras : [];
        savedExtras.forEach((ex) => {
          merged[ex.id] = saved.logs?.[ex.id] || Array.from({ length: ex.target_sets }, emptySet);
          mergedUnits[ex.id] = saved.weightUnits?.[ex.id] || ex.weight_unit;
          mergedTypes[ex.id] = saved.inputTypes?.[ex.id] || ex.input_type;
        });
        setExtras(savedExtras);

        // If there was a saved session with actual logged data, but NONE
        // of its exercise ids exist on the template anymore, the whole
        // routine was regenerated since this session was left in progress
        // (regeneration recreates every TemplateExercise row, so ids never
        // survive a reshuffle). Say so instead of silently showing empty rows.
        if (saved?.logs) {
          const currentIds = new Set(t.exercises.map((ex) => ex.id));
          const savedEntries = Object.entries(saved.logs).filter(([exId]) => !isExtraId(exId));
          const hadLoggedData = savedEntries.some(([, sets]) => sets.some(setHasData));
          const anyStillPresent = savedEntries.some(([exId]) => currentIds.has(Number(exId)));
          if (hadLoggedData && savedEntries.length > 0 && !anyStillPresent) {
            setError(
              "This routine was regenerated since you last worked on it, so your previously logged sets couldn't be matched to the new exercises and weren't restored."
            );
          }
        }

        setLogs(merged);
        setWeightUnits(mergedUnits);
        setInputTypes(mergedTypes);
        setNote(saved?.note || "");
        startedAtRef.current = saved?.startedAt || new Date().toISOString();
        // Marks this workout as in progress, so it can be minimized and found again.
        setActiveWorkout({ templateId: id, title: t.title, startedAt: startedAtRef.current });
      })
      .catch((err) => {
        setError(extractErrorMessage(err));
        // Only a 404 means the template is gone (deleted, or never existed), so only then can
        // its saved session never be resumed. A network error must not throw away logged sets.
        if (err?.response?.status === 404) {
          try {
            localStorage.removeItem(sessionKey(id));
          } catch {
            // ignore
          }
          clearActiveWorkout(id);
        }
      });
  }, [id]);

  // Snapshot to localStorage on every change, so a refresh, a
  // backgrounded/locked phone, or navigating away and back doesn't lose
  // logged sets (or the note, or each exercise's unit and input type).
  useEffect(() => {
    if (!template || !startedAtRef.current) return;
    try {
      localStorage.setItem(
        sessionKey(id),
        JSON.stringify({ startedAt: startedAtRef.current, logs, note, weightUnits, inputTypes, extras })
      );
    } catch {
      // Storage full/unavailable -- non-fatal, just skip persisting this tick.
    }
  }, [logs, note, weightUnits, inputTypes, extras, template, id]);

  // Live elapsed-time ticker, starting once the session's start time is known.
  useEffect(() => {
    if (!startedAtRef.current) return;
    const startMs = new Date(startedAtRef.current).getTime();
    const tick = () => setElapsed(Math.max(0, Math.floor((Date.now() - startMs) / 1000)));
    tick();
    const intervalId = setInterval(tick, 1000);
    return () => clearInterval(intervalId);
  }, [template]);

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
      [exId]: [...prev[exId], emptySet()],
    }));
  }

  function doRemoveSet(exId, setIndex) {
    setLogs((prev) => ({
      ...prev,
      [exId]: prev[exId].filter((_, i) => i !== setIndex),
    }));
  }

  function removeSet(exId, setIndex) {
    const set = logs[exId][setIndex];
    if (!setHasData(set)) {
      doRemoveSet(exId, setIndex);
      return;
    }
    const exerciseName = allExercises.find((ex) => ex.id === exId)?.exercise_name || "this exercise";
    setPendingRemoveSet({ exId, setIndex, exerciseName });
  }

  // Switches one exercise's input unit and converts any already-typed
  // weight values so they still represent the same real weight (e.g.
  // 100 kg becomes ~220.5 lb) instead of just relabeling the number.
  function switchWeightUnit(exId, newUnit) {
    const currentUnit = weightUnits[exId];
    if (!currentUnit || currentUnit === newUnit) return;

    setLogs((prev) => ({
      ...prev,
      [exId]: prev[exId].map((s) => ({
        ...s,
        weight: s.weight === "" ? "" : String(convertWeight(Number(s.weight), currentUnit, newUnit)),
      })),
    }));
    setWeightUnits((prev) => ({ ...prev, [exId]: newUnit }));
  }

  function switchInputType(exId, newType) {
    if (inputTypes[exId] === newType) return;
    setInputTypes((prev) => ({ ...prev, [exId]: newType }));
    // Remember the choice on the routine for next time. Best-effort: the
    // switch already works for this session even if the request fails.
    // (An exercise added just for this workout isn't on the routine, so there is nothing to update.)
    if (!isExtraId(exId)) updateTemplateExercise(template.id, exId, { inputType: newType }).catch(() => {});
  }

  function doDiscardWorkout() {
    restTimer.stop();
    localStorage.removeItem(sessionKey(id));
    clearActiveWorkout(id);
    navigate("/workouts");
  }

  function handleAddExtra(wgerExerciseId, picked) {
    if (allExercises.some((ex) => ex.wger_exercise_id === wgerExerciseId)) {
      showToast(`${picked?.name || "That exercise"} is already in this workout`, "error");
      return;
    }
    const equipment = picked?.equipment || picked?.equipment_name || "";
    const extra = {
      id: `x-${wgerExerciseId}-${Date.now()}`,
      wger_exercise_id: wgerExerciseId,
      exercise_name: picked?.name || "Exercise",
      category_name: picked?.category || "",
      equipment_name: equipment,
      target_sets: 3,
      weight_unit: equipment.toLowerCase().includes("dumbbell") ? "lb" : "kg", // same default routines use
      input_type: "weight_reps",
      extra: true,
    };
    setExtras((prev) => [...prev, extra]);
    setLogs((prev) => ({ ...prev, [extra.id]: Array.from({ length: extra.target_sets }, emptySet) }));
    setWeightUnits((prev) => ({ ...prev, [extra.id]: extra.weight_unit }));
    setInputTypes((prev) => ({ ...prev, [extra.id]: extra.input_type }));
    setShowSearch(false);
    showToast(`Added ${extra.exercise_name} to this workout`, "success");
  }

  function doRemoveExtra(extra) {
    const without = (obj) => Object.fromEntries(Object.entries(obj).filter(([key]) => key !== extra.id));
    setExtras((prev) => prev.filter((ex) => ex.id !== extra.id));
    setLogs(without);
    setWeightUnits(without);
    setInputTypes(without);
  }

  function removeExtra(extra) {
    if ((logs[extra.id] || []).some(setHasData)) setPendingRemoveExtra(extra);
    else doRemoveExtra(extra);
  }

  function handleCancel() {
    const hasProgress = Object.values(logs).some((sets) => sets.some(setHasData));
    if (!hasProgress) {
      doDiscardWorkout();
      return;
    }
    setConfirmingCancel(true);
  }

  // Finishing can't be undone (history isn't editable), so ask first -- but only when something looks
  // unfinished: sets with numbers typed in that were never ticked (those are not saved), or exercises
  // with no ticked set (those are skipped). A clean finish goes straight through.
  function requestFinish() {
    const doneAnywhere = allExercises.some((ex) => (logs[ex.id] || []).some((s) => s.done));
    if (!doneAnywhere) {
      handleFinish(); // shows the "log at least one set" message
      return;
    }
    const unchecked = allExercises.reduce(
      (n, ex) => n + (logs[ex.id] || []).filter((s) => !s.done && setHasData(s)).length,
      0
    );
    const skipped = allExercises.filter((ex) => !(logs[ex.id] || []).some((s) => s.done)).length;
    if (unchecked > 0 || skipped > 0) setFinishWarning({ unchecked, skipped });
    else handleFinish();
  }

  async function handleFinish() {
    setError("");

    const exercises = allExercises
      .map((ex) => {
        const unit = weightUnits[ex.id] || ex.weight_unit;
        const type = inputTypes[ex.id] || ex.input_type || "weight_reps";
        const doneSets = logs[ex.id].filter((s) => s.done);

        // Only fields that make sense for this exercise's type are sent, and
        // each set is checked for valid, in-range numbers here -- the number
        // inputs' min= attributes don't stop someone typing a negative value,
        // and a bad value reaching the backend rejects the whole request.
        let sets_data;
        if (type === "time") {
          sets_data = doneSets.filter(validSeconds).map((s) => ({ seconds: Number(s.seconds) }));
        } else if (type === "reps") {
          sets_data = doneSets.filter(validReps).map((s) => ({ reps: Number(s.reps) }));
        } else {
          // Weight is typed in whichever unit this exercise is set to, but
          // storage is always kg for volume math -- convert lb entries here.
          // display_weight keeps the exact number typed so history can
          // redisplay it without lb<->kg rounding error.
          sets_data = doneSets
            .filter((s) => s.weight !== "" && Number(s.weight) >= 0 && validReps(s))
            .map((s) => ({
              weight: unit === "lb" ? lbToKg(Number(s.weight)) : Number(s.weight),
              display_weight: Number(s.weight),
              reps: Number(s.reps),
            }));
        }

        return { exercise_name: ex.exercise_name, input_type: type, weight_unit: unit, sets_data };
      })
      // Drop exercises with nothing logged -- an exercise that was on the
      // routine but never had a set checked off shouldn't be saved.
      .filter((ex) => ex.sets_data.length > 0);

    if (exercises.length === 0) {
      setError("Log at least one set before finishing the workout.");
      return;
    }

    setFinishing(true);
    try {
      const saved = await finishWorkout({
        templateTitle: template.title,
        startedAt: startedAtRef.current,
        exercises,
        note: note.trim(),
      });
      // Exercises ticked "Also add to routine" are saved to the routine now that the workout is safely
      // recorded. A failure here shouldn't undo the finished workout, so it's ignored.
      const keep = extras.filter((ex) => ex.addToRoutine && exercises.some((e) => e.exercise_name === ex.exercise_name));
      await Promise.all(keep.map((ex) => addExerciseToTemplate(template.id, { wgerExerciseId: ex.wger_exercise_id }).catch(() => {})));
      restTimer.stop();
      localStorage.removeItem(sessionKey(id));
      clearActiveWorkout(id);
      const summary = buildSummary({
        title: template.title,
        startedAt: startedAtRef.current,
        exercises,
        historyId: saved?.id,
      });
      navigate("/workouts/complete", { replace: true, state: { summary } });
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

  if (showSearch) {
    return (
      <ExerciseSearch
        // Generated routines only offer beginner-safe suggestions; your own routines allow any exercise.
        templateId={template.is_generated ? template.id : null}
        onSuggest={null}
        onAdd={handleAddExtra}
        onClose={() => setShowSearch(false)}
      />
    );
  }

  return (
    <div className="page active-workout">
      <PageHeader
        title={template.title}
        back
        onBack={() => navigate("/workouts")}
        action={
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span className="pill pill-neutral stat" style={{ fontSize: 13, whiteSpace: "nowrap" }} aria-label="Workout time">
              {formatElapsed(elapsed)}
            </span>
            <button
              className="btn-ghost"
              onClick={handleCancel}
              aria-label="Discard workout"
              title="Discard workout"
              style={{ padding: 6, display: "flex", color: "var(--chili)" }}
            >
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M3 6h18M8 6V4h8v2M6 6l1 14h10l1-14M10 11v6M14 11v6" />
              </svg>
            </button>
            <button className="btn btn-primary" style={{ padding: "8px 14px", fontSize: 13 }} onClick={requestFinish} disabled={finishing}>
              {finishing ? "Saving..." : "Finish"}
            </button>
          </div>
        }
      />

      <ErrorBanner message={error} />

      {allExercises.map((ex) => {
        const unit = weightUnits[ex.id] || ex.weight_unit;
        const type = inputTypes[ex.id] || ex.input_type || "weight_reps";
        const cols = gridCols(type);
        return (
          <div key={ex.id} className="card">
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 2, gap: 8 }}>
              <div>
                <p style={{ fontWeight: 600, marginBottom: 2 }}>{ex.exercise_name}</p>
                <p style={{ fontSize: 12, color: "var(--text-faint)" }}>
                  {ex.category_name}{ex.extra ? " · Added for this workout" : ""}
                </p>
              </div>
              {type === "weight_reps" && (
                <UnitToggle
                  options={[{ value: "kg", label: "kg" }, { value: "lb", label: "lb" }]}
                  value={unit}
                  onChange={(v) => switchWeightUnit(ex.id, v)}
                />
              )}
            </div>

            <select
              aria-label="Log this exercise as"
              value={type}
              onChange={(e) => switchInputType(ex.id, e.target.value)}
              style={{ height: 30, minHeight: 30, width: "auto", fontSize: 12, padding: "0 30px 0 10px", marginTop: 6 }}
            >
              {INPUT_TYPES.map(([value, label]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>

            <div style={{ display: "grid", gridTemplateColumns: cols, gap: 8, fontSize: 11, color: "var(--text-faint)", margin: "12px 0 6px" }}>
              <span>#</span>
              {type === "weight_reps" && <span>Weight ({unit})</span>}
              {type !== "time" && <span>Reps</span>}
              {type === "time" && <span>Seconds</span>}
              <span></span>
              <span></span>
            </div>

            {logs[ex.id]?.map((set, i) => (
              <div key={i} style={{ display: "grid", gridTemplateColumns: cols, gap: 8, alignItems: "center", marginBottom: 8 }}>
                <span className="stat" style={{ fontSize: 13, color: "var(--text-dim)" }}>{i + 1}</span>
                {type === "weight_reps" && (
                  <input type="number" min="0" step="any" value={set.weight} onChange={(e) => updateSet(ex.id, i, "weight", e.target.value)} placeholder="0" style={{ padding: "8px 10px" }} />
                )}
                {type !== "time" && (
                  <input type="number" min="1" step="1" value={set.reps} onChange={(e) => updateSet(ex.id, i, "reps", e.target.value)} placeholder="0" style={{ padding: "8px 10px" }} />
                )}
                {type === "time" && (
                  <input type="number" min="1" step="1" value={set.seconds ?? ""} onChange={(e) => updateSet(ex.id, i, "seconds", e.target.value)} placeholder="0" style={{ padding: "8px 10px" }} />
                )}
                <button
                  onClick={() => {
                    // Start the rest only when marking a set done, not when un-checking it.
                    // Runs inside the tap, which also unlocks the beep on phones.
                    if (!set.done && restTimer.autoStart) restTimer.start(restTimer.duration);
                    toggleDone(ex.id, i);
                  }}
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

            {ex.extra && !template.is_generated && (
              <label style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 8, fontSize: 13, color: "var(--text-dim)", cursor: "pointer" }}>
                <input
                  type="checkbox"
                  checked={!!ex.addToRoutine}
                  onChange={(e) =>
                    setExtras((prev) => prev.map((x) => (x.id === ex.id ? { ...x, addToRoutine: e.target.checked } : x)))
                  }
                  style={{ width: "auto", margin: 0 }}
                />
                Also add to this routine when I finish
              </label>
            )}

            {ex.extra && (
              <button
                className="btn-ghost"
                onClick={() => removeExtra(ex)}
                style={{ width: "100%", padding: "8px", marginTop: 4, color: "var(--chili)", fontSize: 13 }}
              >
                Remove exercise
              </button>
            )}
          </div>
        );
      })}

      <button className="btn btn-secondary btn-block" onClick={() => setShowSearch(true)}>
        + Add Exercise
      </button>

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

      <RestTimer timer={restTimer} />

      <ConfirmDialog
        open={pendingRemoveSet !== null}
        title="Remove set"
        message={pendingRemoveSet ? `Remove this set of ${pendingRemoveSet.exerciseName}? Logged data will be lost.` : ""}
        confirmLabel="Remove"
        onConfirm={() => {
          doRemoveSet(pendingRemoveSet.exId, pendingRemoveSet.setIndex);
          setPendingRemoveSet(null);
        }}
        onCancel={() => setPendingRemoveSet(null)}
      />
      <ConfirmDialog
        open={pendingRemoveExtra !== null}
        title="Remove exercise"
        message={pendingRemoveExtra ? `Remove ${pendingRemoveExtra.exercise_name} from this workout? Logged sets will be lost.` : ""}
        confirmLabel="Remove"
        onConfirm={() => {
          doRemoveExtra(pendingRemoveExtra);
          setPendingRemoveExtra(null);
        }}
        onCancel={() => setPendingRemoveExtra(null)}
      />
      <ConfirmDialog
        open={finishWarning !== null}
        title="Finish workout?"
        message={
          finishWarning
            ? [
                finishWarning.unchecked > 0 &&
                  `${finishWarning.unchecked} set${finishWarning.unchecked === 1 ? " has" : "s have"} numbers entered but ${finishWarning.unchecked === 1 ? "isn't" : "aren't"} checked off, so ${finishWarning.unchecked === 1 ? "it" : "they"} won't be saved.`,
                finishWarning.skipped > 0 &&
                  `${finishWarning.skipped} exercise${finishWarning.skipped === 1 ? " has" : "s have"} no sets checked off and will be skipped.`,
                "Are you sure you want to finish this workout?",
              ]
                .filter(Boolean)
                .join(" ")
            : ""
        }
        confirmLabel="Finish"
        cancelLabel="Keep going"
        onConfirm={() => {
          setFinishWarning(null);
          handleFinish();
        }}
        onCancel={() => setFinishWarning(null)}
      />
      <ConfirmDialog
        open={confirmingCancel}
        title="Discard workout"
        message="Discard this workout? Logged sets will be lost."
        confirmLabel="Discard"
        onConfirm={() => { setConfirmingCancel(false); doDiscardWorkout(); }}
        onCancel={() => setConfirmingCancel(false)}
      />
    </div>
  );
}