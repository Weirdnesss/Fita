// Builds the numbers for the "workout complete" screen from the same payload that is
// sent to the backend, so what is shown always matches what was saved.
// exercises: [{ exercise_name, input_type, weight_unit, sets_data }] (weights in kg)

function clock(totalSeconds) {
  const m = Math.floor(totalSeconds / 60);
  const s = totalSeconds % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

function describe(ex) {
  const sets = ex.sets_data;
  const count = `${sets.length} ${sets.length === 1 ? "set" : "sets"}`;
  if (ex.input_type === "time") {
    return `${count} · ${clock(sets.reduce((n, s) => n + s.seconds, 0))} total`;
  }
  if (ex.input_type === "reps") {
    return `${count} · ${sets.reduce((n, s) => n + s.reps, 0)} reps`;
  }
  // Best set = heaviest weight (most reps breaks a tie), shown in the unit it was typed in.
  const best = sets.reduce((a, b) => (b.weight > a.weight || (b.weight === a.weight && b.reps > a.reps) ? b : a));
  return `${count} · best ${best.display_weight} ${ex.weight_unit} × ${best.reps}`;
}

export function buildSummary({ title, startedAt, exercises, historyId }) {
  const durationSeconds = Math.max(0, Math.floor((Date.now() - new Date(startedAt).getTime()) / 1000));
  let totalSets = 0;
  let volumeKg = 0;
  for (const ex of exercises) {
    totalSets += ex.sets_data.length;
    if (ex.input_type === "weight_reps") {
      for (const s of ex.sets_data) volumeKg += s.weight * s.reps;
    }
  }
  return {
    title,
    historyId: historyId ?? null,
    durationSeconds,
    totalSets,
    volumeKg: Math.round(volumeKg),
    exercises: exercises.map((ex) => ({ name: ex.exercise_name, detail: describe(ex) })),
  };
}
