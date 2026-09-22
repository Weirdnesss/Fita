import { useEffect, useState } from "react";
import { Loading, ErrorBanner, EmptyState, extractErrorMessage } from "../../components/Status";
import { getWorkoutTrends, getExerciseFrequency, getExerciseProgression } from "../../api/workouts";

const PERIODS = [
  ["week", "This Week"],
  ["month", "This Month"],
];

const PROGRESSION_PERIODS = [
  ["month", "30 Days"],
  ["3months", "3 Months"],
  ["all", "All Time"],
];

// Unlike Routines/History, Trends can't just be sliced from data the
// dashboard already fetched on mount -- it's its own period-scoped
// query. So this panel fetches lazily on its own first mount (i.e.
// the first time the Trends tab is opened) rather than eagerly
// alongside templates/history, and re-fetches only when the period
// changes from there.
export default function WorkoutTrendsPanel() {
  const [period, setPeriod] = useState("week");
  const [trends, setTrends] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    setTrends(null);
    setError("");
    getWorkoutTrends(period)
      .then(setTrends)
      .catch((err) => setError(extractErrorMessage(err)));
  }, [period]);

  return (
    <div className="workout-trends">
      <ErrorBanner message={error} />

      <div style={{ display: "flex", gap: 8 }}>
        {PERIODS.map(([value, label]) => (
          <button
            key={value}
            className={period === value ? "btn btn-primary" : "btn btn-secondary"}
            style={{ flex: 1 }}
            onClick={() => setPeriod(value)}
          >
            {label}
          </button>
        ))}
      </div>

      {!trends && !error && <Loading />}

      {trends && (
        <>
          <div style={{ display: "flex", gap: 10 }}>
            <div className="card" style={{ flex: 1, textAlign: "center" }}>
              <div className="stat" style={{ fontSize: 20, color: trends.current_streak > 0 ? "var(--chili)" : "var(--text)" }}>
                {trends.current_streak}
              </div>
              <div className="eyebrow">Day Streak</div>
            </div>
            <div className="card" style={{ flex: 1, textAlign: "center" }}>
              <div className="stat" style={{ fontSize: 20 }}>{trends.total_workouts}</div>
              <div className="eyebrow">Workouts</div>
            </div>
          </div>

          {trends.days_logged === 0 ? (
            <div className="card" style={{ textAlign: "center" }}>
              <p style={{ fontSize: 13, color: "var(--text-faint)" }}>
                No workouts logged yet {period === "week" ? "this week" : "this month"} -- finish
                a workout to see your trends.
              </p>
            </div>
          ) : (
            <>
              <div className="card">
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 2 }}>
                  <p style={{ fontWeight: 600 }}>Volume</p>
                  {trends.volume_change_pct !== null && (
                    <span style={{ fontSize: 12, fontWeight: 600, color: trends.volume_change_pct >= 0 ? "var(--bamboo)" : "var(--chili)" }}>
                      {trends.volume_change_pct >= 0 ? "↑" : "↓"} {Math.abs(trends.volume_change_pct)}% vs last {period}
                    </span>
                  )}
                </div>
                <p style={{ fontSize: 11, color: "var(--text-faint)", marginBottom: 10 }}>
                  Total weight × reps across all your sets each day
                </p>
                <VolumeBarChart days={trends.days} />
              </div>

              <div className="card">
                <p style={{ fontWeight: 600, marginBottom: 10 }}>
                  Averages <span style={{ fontWeight: 400, fontSize: 12, color: "var(--text-faint)" }}>(on workout days)</span>
                </p>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 8, textAlign: "center" }}>
                  <StatBox label="Volume" value={`${Math.round(trends.averages.volume).toLocaleString()} kg`} />
                  <StatBox label="Sets" value={trends.averages.sets} />
                </div>
              </div>
            </>
          )}

          <ExerciseProgressionSection />
        </>
      )}
    </div>
  );
}

function ExerciseProgressionSection() {
  const [exercises, setExercises] = useState(null);
  const [selected, setSelected] = useState("");
  const [progPeriod, setProgPeriod] = useState("3months");
  const [progression, setProgression] = useState(null);
  const [progError, setProgError] = useState("");

  useEffect(() => {
    getExerciseFrequency()
      .then((list) => {
        setExercises(list);
        if (list.length > 0) setSelected(list[0].name);
      })
      .catch((err) => setProgError(extractErrorMessage(err)));
  }, []);

  useEffect(() => {
    if (!selected) return;
    setProgression(null);
    getExerciseProgression(selected, progPeriod)
      .then(setProgression)
      .catch((err) => setProgError(extractErrorMessage(err)));
  }, [selected, progPeriod]);

  if (exercises === null) return null; // still loading the picker -- avoid a flash of an empty section
  if (exercises.length === 0) {
    return (
      <div className="card">
        <p style={{ fontWeight: 600, marginBottom: 4 }}>Progress</p>
        <EmptyState title="Log a few workouts to see your progression on specific exercises" />
      </div>
    );
  }

  const sessions = progression?.sessions || [];
  const latest = sessions[sessions.length - 1];
  const first = sessions[0];
  const change = sessions.length >= 2 ? latest.top_weight - first.top_weight : null;

  return (
    <div className="card">
      <p style={{ fontWeight: 600, marginBottom: 2 }}>Progress</p>
      <p style={{ fontSize: 11, color: "var(--text-faint)", marginBottom: 10 }}>
        Your heaviest set each session
      </p>

      <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
        <select value={selected} onChange={(e) => setSelected(e.target.value)} style={{ flex: 1 }}>
          {exercises.map((ex) => (
            <option key={ex.name} value={ex.name}>{ex.name}</option>
          ))}
        </select>
      </div>

      <div style={{ display: "flex", gap: 6, marginBottom: 12 }}>
        {PROGRESSION_PERIODS.map(([value, label]) => (
          <button
            key={value}
            className={progPeriod === value ? "btn btn-primary" : "btn btn-secondary"}
            style={{ flex: 1, padding: "6px 8px", fontSize: 11 }}
            onClick={() => setProgPeriod(value)}
          >
            {label}
          </button>
        ))}
      </div>

      <ErrorBanner message={progError} />

      {!progression && !progError && <Loading />}

      {progression && sessions.length === 0 && (
        <EmptyState title={`No ${selected} logged in this period`} />
      )}

      {progression && sessions.length > 0 && (
        <>
          <ProgressionChart sessions={sessions} />
          <div style={{ display: "flex", justifyContent: "space-between", marginTop: 10, fontSize: 12 }}>
            <span style={{ color: "var(--text-faint)" }}>
              Latest: <strong style={{ color: "var(--text)" }}>{latest.top_weight}kg × {latest.top_weight_reps}</strong>
            </span>
            {change !== null && (
              <span style={{ color: change >= 0 ? "var(--bamboo)" : "var(--chili)" }}>
                {change >= 0 ? "↑" : "↓"} {Math.abs(change)}kg since {formatShortDate(first.date)}
              </span>
            )}
          </div>
        </>
      )}
    </div>
  );
}

function ProgressionChart({ sessions }) {
  const width = 300;
  const height = 110;
  const padX = 12;
  const padY = 14;

  const weights = sessions.map((s) => s.top_weight);
  const minW = Math.min(...weights);
  const maxW = Math.max(...weights);
  const range = maxW - minW || 1;

  const points = sessions.map((s, i) => {
    const x = sessions.length === 1 ? width / 2 : padX + (i / (sessions.length - 1)) * (width - padX * 2);
    const y = height - padY - ((s.top_weight - minW) / range) * (height - padY * 2);
    return { x, y, ...s };
  });

  const pathD = points.map((p, i) => `${i === 0 ? "M" : "L"}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");

  return (
    <svg viewBox={`0 0 ${width} ${height}`} style={{ width: "100%", height, display: "block" }}>
      {points.length > 1 && <path d={pathD} fill="none" stroke="var(--bamboo)" strokeWidth="2" />}
      {points.map((p, i) => (
        <circle key={i} cx={p.x} cy={p.y} r="3.5" fill="var(--bamboo)">
          <title>{`${formatShortDate(p.date)}: ${p.top_weight}kg \u00d7 ${p.top_weight_reps}`}</title>
        </circle>
      ))}
    </svg>
  );
}

function VolumeBarChart({ days }) {
  const maxValue = Math.max(...days.map((d) => d.volume), 1);
  const isMonth = days.length > 7;
  return (
    <div style={{ display: "flex", alignItems: "flex-end", gap: isMonth ? 2 : 6, height: 120 }}>
      {days.map((d) => {
        const pct = Math.min((d.volume / maxValue) * 100, 100);
        return (
          <div key={d.date} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", height: "100%", justifyContent: "flex-end", gap: 4 }}>
            <div
              style={{
                width: "100%",
                height: `${pct}%`,
                minHeight: d.logged ? 3 : 0,
                borderRadius: 2,
                background: d.logged ? "var(--bamboo)" : "var(--bg-raised)",
              }}
              title={`${formatShortDate(d.date)}: ${Math.round(d.volume).toLocaleString()} kg${d.workouts > 1 ? ` across ${d.workouts} workouts` : ""}`}
            />
            {!isMonth && <span style={{ fontSize: 9, color: "var(--text-faint)" }}>{formatShortDate(d.date)}</span>}
          </div>
        );
      })}
    </div>
  );
}

function formatShortDate(dateStr) {
  const date = new Date(dateStr + "T00:00:00");
  return date.toLocaleDateString(undefined, { weekday: "narrow" });
}

function StatBox({ label, value }) {
  return (
    <div style={{ background: "var(--bg-raised)", borderRadius: "var(--radius-sm)", padding: "10px 4px" }}>
      <div className="stat" style={{ fontSize: 15 }}>{value}</div>
      <div className="eyebrow" style={{ marginTop: 4 }}>{label}</div>
    </div>
  );
}