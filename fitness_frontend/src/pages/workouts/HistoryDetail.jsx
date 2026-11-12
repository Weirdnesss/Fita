import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import PageHeader from "../../components/PageHeader";
import { Loading, ErrorBanner, extractErrorMessage } from "../../components/Status";
import { getHistoryDetail, updateHistory, deleteHistory, kgToLb, lbToKg } from "../../api/workouts";
import { formatSeconds } from "../../lib/formatSets";
import StickyBar from "../../components/StickyBar";
import ConfirmDialog from "../../components/ConfirmDialog";
import { useToast } from "../../context/ToastContext";

// Draft values are kept as strings while typing, in the unit the exercise was logged in.
function draftFromHistory(history) {
  const drafts = {};
  for (const ex of history.performed_exercises) {
    const isLb = ex.weight_unit === "lb";
    drafts[ex.id] = ex.sets_data.map((s) => ({
      weight: String(s.display_weight !== undefined ? s.display_weight : isLb ? kgToLb(s.weight) : s.weight ?? ""),
      reps: s.reps !== undefined ? String(s.reps) : "",
      seconds: s.seconds !== undefined ? String(s.seconds) : "",
    }));
  }
  return drafts;
}

const isPosInt = (v) => v !== "" && Number.isInteger(Number(v)) && Number(v) >= 1;

export default function HistoryDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const showToast = useToast();
  const [history, setHistory] = useState(null);
  const [error, setError] = useState("");
  const [editing, setEditing] = useState(false);
  const [drafts, setDrafts] = useState({}); // { performedExerciseId: [{ weight, reps, seconds }] }
  const [noteDraft, setNoteDraft] = useState("");
  const [saving, setSaving] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);

  useEffect(() => {
    getHistoryDetail(id)
      .then(setHistory)
      .catch((err) => setError(extractErrorMessage(err)));
  }, [id]);

  if (!history) {
    return (
      <div className="page history-detail">
        <PageHeader title="Loading" back backTo="/workouts" />
        <ErrorBanner message={error} />
        {!error && <Loading />}
      </div>
    );
  }

  function startEdit() {
    setDrafts(draftFromHistory(history));
    setNoteDraft(history.note || "");
    setError("");
    setEditing(true);
  }

  function setField(exId, index, field, value) {
    setDrafts((prev) => ({
      ...prev,
      [exId]: prev[exId].map((row, i) => (i === index ? { ...row, [field]: value } : row)),
    }));
  }

  function removeSet(exId, index) {
    setDrafts((prev) => ({ ...prev, [exId]: prev[exId].filter((_, i) => i !== index) }));
  }

  async function saveEdit() {
    const exercises = [];
    for (const ex of history.performed_exercises) {
      const type = ex.input_type || "weight_reps";
      const isLb = ex.weight_unit === "lb";
      const rows = drafts[ex.id] || [];
      const sets_data = [];
      for (const row of rows) {
        if (type === "time") {
          if (!isPosInt(row.seconds) || Number(row.seconds) > 7200) return setError(`Check the time entered for ${ex.exercise_name}.`);
          sets_data.push({ seconds: Number(row.seconds) });
        } else if (type === "reps") {
          if (!isPosInt(row.reps)) return setError(`Reps for ${ex.exercise_name} must be a whole number of 1 or more.`);
          sets_data.push({ reps: Number(row.reps) });
        } else {
          if (row.weight === "" || !(Number(row.weight) >= 0) || !isPosInt(row.reps)) {
            return setError(`Check the weight and reps entered for ${ex.exercise_name}.`);
          }
          // Stored in kg for volume math; display_weight keeps exactly what was typed.
          sets_data.push({
            weight: isLb ? lbToKg(Number(row.weight)) : Number(row.weight),
            display_weight: Number(row.weight),
            reps: Number(row.reps),
          });
        }
      }
      exercises.push({ id: ex.id, sets_data });
    }

    setSaving(true);
    setError("");
    try {
      const updated = await updateHistory(history.id, { note: noteDraft.trim(), exercises });
      setHistory(updated);
      setEditing(false);
      showToast("Workout updated", "success");
    } catch (err) {
      setError(extractErrorMessage(err, "Couldn't save your changes."));
    } finally {
      setSaving(false);
    }
  }

  async function confirmDelete() {
    setConfirmingDelete(false);
    try {
      await deleteHistory(history.id);
      showToast("Workout deleted", "success");
      navigate("/workouts", { replace: true });
    } catch (err) {
      setError(extractErrorMessage(err, "Couldn't delete this workout."));
    }
  }

  return (
    <div className="page">
      <PageHeader
        title={history.template_title}
        subtitle={new Date(history.completed_at).toLocaleString()}
        back
        backTo="/workouts"
        action={
          editing ? (
            <div style={{ display: "flex", gap: 8 }}>
              <button className="btn btn-secondary" style={{ padding: "8px 14px", fontSize: 13 }} onClick={() => { setEditing(false); setError(""); }} disabled={saving}>
                Cancel
              </button>
              <button className="btn btn-primary" style={{ padding: "8px 14px", fontSize: 13 }} onClick={saveEdit} disabled={saving}>
                {saving ? "Saving..." : "Save"}
              </button>
            </div>
          ) : history.is_editable ? (
            <button className="btn btn-secondary" style={{ padding: "8px 14px", fontSize: 13 }} onClick={startEdit}>
              Edit
            </button>
          ) : null
        }
      />
      <ErrorBanner message={error} />

      <StickyBar>
      <div className="card" style={{ marginBottom: 16 }}>
        <div style={{ display: "flex", gap: 24 }}>
          <MiniStat label="Duration" value={`${history.duration_minutes} min`} />
          <MiniStat label="Exercises" value={history.total_exercises} />
          <MiniStat label="Sets" value={history.total_sets} />
        </div>
      </div>
      </StickyBar>

      {editing ? (
        <div className="card" style={{ marginBottom: 16 }}>
          <label htmlFor="history-note" style={{ fontSize: 12, color: "var(--text-faint)" }}>Note</label>
          <textarea id="history-note" rows={3} maxLength={1000} value={noteDraft} onChange={(e) => setNoteDraft(e.target.value)} />
        </div>
      ) : history.note && (
        <div className="card" style={{ marginBottom: 16 }}>
          <p style={{ fontSize: 12, color: "var(--text-faint)", marginBottom: 4 }}>Note</p>
          <p style={{ fontSize: 14, whiteSpace: "pre-wrap" }}>{history.note}</p>
        </div>
      )}

      {history.performed_exercises.map((ex) => {
        // What was logged depends on the exercise's input type. For
        // weight_reps, sets_data.weight and total_volume are always stored
        // in kg; convert to the unit that was displayed when it was logged.
        // Individual sets prefer display_weight (the exact number typed)
        // so there's no lb<->kg rounding on redisplay -- older history
        // without that field falls back to converting the kg value.
        const type = ex.input_type || "weight_reps";
        const isLb = ex.weight_unit === "lb";
        const displayVolume = isLb ? kgToLb(ex.total_volume) : ex.total_volume;
        const totalReps = ex.sets_data.reduce((sum, s) => sum + (s.reps || 0), 0);
        const totalSeconds = ex.sets_data.reduce((sum, s) => sum + (s.seconds || 0), 0);

        const pill =
          type === "time"
            ? `${formatSeconds(totalSeconds)} total`
            : type === "reps"
            ? `${totalReps} total reps`
            : `${displayVolume} ${ex.weight_unit} volume`;
        const cols = editing
          ? type === "weight_reps" ? "24px 1fr 1fr 32px" : "24px 1fr 32px"
          : type === "weight_reps" ? "24px 1fr 1fr" : "24px 1fr";
        const rows = editing ? drafts[ex.id] || [] : ex.sets_data;

        return (
          <div key={ex.id} className="card" style={{ marginBottom: 10 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 12 }}>
              <p style={{ fontWeight: 600 }}>{ex.exercise_name}</p>
              {!editing && <span className="pill pill-bamboo">{pill}</span>}
            </div>

            <div style={{ display: "grid", gridTemplateColumns: cols, gap: 8, fontSize: 11, color: "var(--text-faint)", marginBottom: 6 }}>
              <span>#</span>
              {type === "weight_reps" && <span>Weight ({ex.weight_unit})</span>}
              {type !== "time" && <span>Reps</span>}
              {type === "time" && <span>{editing ? "Seconds" : "Time"}</span>}
              {editing && <span />}
            </div>

            {editing && rows.map((row, i) => (
              <div key={i} style={{ display: "grid", gridTemplateColumns: cols, gap: 8, alignItems: "center", marginBottom: 6 }}>
                <span className="stat" style={{ fontSize: 13, color: "var(--text-dim)" }}>{i + 1}</span>
                {type === "weight_reps" && (
                  <input type="number" inputMode="decimal" min="0" step="any" aria-label={`Set ${i + 1} weight`}
                    value={row.weight} onChange={(e) => setField(ex.id, i, "weight", e.target.value)} />
                )}
                {type !== "time" && (
                  <input type="number" inputMode="numeric" min="1" step="1" aria-label={`Set ${i + 1} reps`}
                    value={row.reps} onChange={(e) => setField(ex.id, i, "reps", e.target.value)} />
                )}
                {type === "time" && (
                  <input type="number" inputMode="numeric" min="1" max="7200" step="1" aria-label={`Set ${i + 1} seconds`}
                    value={row.seconds} onChange={(e) => setField(ex.id, i, "seconds", e.target.value)} />
                )}
                {rows.length > 1 ? (
                  <button className="btn-ghost" aria-label={`Remove set ${i + 1}`} onClick={() => removeSet(ex.id, i)}
                    style={{ color: "var(--chili)", fontSize: 18, padding: 0, lineHeight: 1 }}>
                    ×
                  </button>
                ) : <span />}
              </div>
            ))}

            {!editing && ex.sets_data.map((set, i) => (
              <div key={i} style={{ display: "grid", gridTemplateColumns: cols, gap: 8, alignItems: "center", marginBottom: 6 }}>
                <span className="stat" style={{ fontSize: 13, color: "var(--text-dim)" }}>{i + 1}</span>
                {type === "weight_reps" && (
                  <span style={{ fontSize: 14 }}>
                    {set.display_weight !== undefined ? set.display_weight : (isLb ? kgToLb(set.weight) : set.weight)}
                  </span>
                )}
                {type !== "time" && <span style={{ fontSize: 14 }}>{set.reps}</span>}
                {type === "time" && <span style={{ fontSize: 14 }}>{formatSeconds(set.seconds)}</span>}
              </div>
            ))}
          </div>
        );
      })}

      {!editing && (
        <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 6 }}>
          {!history.is_editable && (
            <p style={{ fontSize: 12, color: "var(--text-faint)" }}>
              Workouts can be edited for 7 days after they're finished.
            </p>
          )}
          <button className="btn-ghost" style={{ color: "var(--chili)", fontSize: 13, alignSelf: "flex-start" }} onClick={() => setConfirmingDelete(true)}>
            Delete workout
          </button>
        </div>
      )}

      <ConfirmDialog
        open={confirmingDelete}
        title="Delete workout"
        message="Delete this workout from your history? It will no longer count toward your progress. This can't be undone."
        confirmLabel="Delete"
        onConfirm={confirmDelete}
        onCancel={() => setConfirmingDelete(false)}
      />
    </div>
  );
}

function MiniStat({ label, value }) {
  return (
    <div>
      <div className="stat" style={{ fontSize: 15 }}>{value}</div>
      <div className="eyebrow">{label}</div>
    </div>
  );
}