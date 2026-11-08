import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import PageHeader from "../../components/PageHeader";
import { Loading, ErrorBanner, extractErrorMessage } from "../../components/Status";
import { getHistoryDetail, kgToLb } from "../../api/workouts";
import { formatSeconds } from "../../lib/formatSets";
import StickyBar from "../../components/StickyBar";

export default function HistoryDetail() {
  const { id } = useParams();
  const [history, setHistory] = useState(null);
  const [error, setError] = useState("");

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

  return (
    <div className="page">
      <PageHeader
        title={history.template_title}
        subtitle={new Date(history.completed_at).toLocaleString()}
        back
        backTo="/workouts"
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

      {history.note && (
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
        const cols = type === "weight_reps" ? "24px 1fr 1fr" : "24px 1fr";

        return (
          <div key={ex.id} className="card" style={{ marginBottom: 10 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 12 }}>
              <p style={{ fontWeight: 600 }}>{ex.exercise_name}</p>
              <span className="pill pill-bamboo">{pill}</span>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: cols, gap: 8, fontSize: 11, color: "var(--text-faint)", marginBottom: 6 }}>
              <span>#</span>
              {type === "weight_reps" && <span>Weight ({ex.weight_unit})</span>}
              {type !== "time" && <span>Reps</span>}
              {type === "time" && <span>Time</span>}
            </div>

            {ex.sets_data.map((set, i) => (
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