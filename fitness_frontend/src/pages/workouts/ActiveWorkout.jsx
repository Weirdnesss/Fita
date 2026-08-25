import { useEffect, useState, useRef } from "react";
import { useNavigate, useParams } from "react-router-dom";
import PageHeader from "../../components/PageHeader";
import { Loading, ErrorBanner, extractErrorMessage } from "../../components/Status";
import { getTemplate, finishWorkout } from "../../api/workouts";

export default function ActiveWorkout() {
  const { id } = useParams();
  const navigate = useNavigate();
  const startedAtRef = useRef(new Date().toISOString());

  const [template, setTemplate] = useState(null);
  const [logs, setLogs] = useState({}); // exerciseId -> [{weight, reps, done}]
  const [error, setError] = useState("");
  const [finishing, setFinishing] = useState(false);

  useEffect(() => {
    getTemplate(id)
      .then((t) => {
        setTemplate(t);
        const initial = {};
        t.exercises.forEach((ex) => {
          initial[ex.id] = Array.from({ length: ex.target_sets }, () => ({ weight: "", reps: "", done: false }));
        });
        setLogs(initial);
      })
      .catch((err) => setError(extractErrorMessage(err)));
  }, [id]);

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

  async function handleFinish() {
    setFinishing(true);
    setError("");
    try {
      const exercises = template.exercises.map((ex) => ({
        exercise_name: ex.exercise_name,
        sets_data: logs[ex.id]
          .filter((s) => s.done && s.weight !== "" && s.reps !== "")
          .map((s) => ({ weight: Number(s.weight), reps: Number(s.reps) })),
      }));

      await finishWorkout({
        templateTitle: template.title,
        startedAt: startedAtRef.current,
        exercises,
      });
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
        <PageHeader title="Loading" back />
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
        action={
          <button className="btn btn-primary" style={{ padding: "8px 14px", fontSize: 13 }} onClick={handleFinish} disabled={finishing}>
            {finishing ? "Saving..." : "Finish Workout"}
          </button>
        }
      />
      <ErrorBanner message={error} />

      {template.exercises.map((ex) => (
        <div key={ex.id} className="card">
          <p style={{ fontWeight: 600, marginBottom: 2 }}>{ex.exercise_name}</p>
          <p style={{ fontSize: 12, color: "var(--text-faint)", marginBottom: 12 }}>{ex.category_name}</p>

          <div style={{ display: "grid", gridTemplateColumns: "24px 1fr 1fr 32px", gap: 8, fontSize: 11, color: "var(--text-faint)", marginBottom: 6 }}>
            <span>#</span>
            <span>Weight (kg)</span>
            <span>Reps</span>
            <span></span>
          </div>

          {logs[ex.id]?.map((set, i) => (
            <div key={i} style={{ display: "grid", gridTemplateColumns: "24px 1fr 1fr 32px", gap: 8, alignItems: "center", marginBottom: 8 }}>
              <span className="stat" style={{ fontSize: 13, color: "var(--text-dim)" }}>{i + 1}</span>
              <input type="number" value={set.weight} onChange={(e) => updateSet(ex.id, i, "weight", e.target.value)} placeholder="0" style={{ padding: "8px 10px" }} />
              <input type="number" value={set.reps} onChange={(e) => updateSet(ex.id, i, "reps", e.target.value)} placeholder="0" style={{ padding: "8px 10px" }} />
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
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}
