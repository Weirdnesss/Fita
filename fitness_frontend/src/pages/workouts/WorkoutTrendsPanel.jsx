import { useEffect, useState } from "react";
import { Loading, ErrorBanner, EmptyState, extractErrorMessage } from "../../components/Status";
import SegmentedControl from "../../components/SegmentedControl";
import { useWidth } from "../../lib/useWidth";
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

// date-only strings need a time added or some timezones show the day before
const parse = (s) => new Date(`${s}T00:00:00`);
const toTime = (s) => parse(s).getTime();
const shortDate = (s) => parse(s).toLocaleDateString(undefined, { month: "short", day: "numeric" });
const fullDate = (s) => parse(s).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
const dayLabel = (s) => parse(s).toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" });
const weekdayLetter = (s) => parse(s).toLocaleDateString(undefined, { weekday: "narrow" });
const round1 = (n) => Math.round(n * 10) / 10;

// Unlike Routines/History, Trends can't just be sliced from data the
// dashboard already fetched on mount -- it's its own period-scoped
// query. So this panel fetches lazily on its own first mount (i.e.
// the first time the Trends tab is opened) rather than eagerly
// alongside templates/history, and re-fetches only when the period
// changes from there. Old data stays on screen (dimmed) while the new
// period loads, so switching doesn't blank and remount everything.
export default function WorkoutTrendsPanel() {
  const [period, setPeriod] = useState("week");
  const [trends, setTrends] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError("");
    getWorkoutTrends(period)
      .then((t) => { if (!cancelled) setTrends(t); })
      .catch((err) => { if (!cancelled) setError(extractErrorMessage(err)); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [period]);

  return (
    <div className="workout-trends">
      <ErrorBanner message={error} />

      <div style={{ display: "flex", justifyContent: "flex-end" }}>
        <SegmentedControl options={PERIODS} value={period} onChange={setPeriod} />
      </div>

      {!trends && !error && <Loading />}

      {trends && (
        <div style={{ display: "flex", flexDirection: "column", gap: 16, opacity: loading ? 0.5 : 1, transition: "opacity 0.15s ease" }}>
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
                  {trends.volume_change_pct != null && (
                    <span style={{ fontSize: 12, fontWeight: 600, color: trends.volume_change_pct >= 0 ? "var(--bamboo)" : "var(--chili)" }}>
                      {trends.volume_change_pct >= 0 ? "↑" : "↓"} {Math.abs(trends.volume_change_pct)}% vs last {period}
                    </span>
                  )}
                </div>
                <p style={{ fontSize: 11, color: "var(--text-faint)", marginBottom: 10 }}>
                  Total weight × reps across all your sets each day
                </p>
                <VolumeBarChart days={trends.days} resetKey={period} />
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
        </div>
      )}

      {/* Independent of the week/month toggle, so it lives outside the
          block above and keeps its own state when the period changes. */}
      <ExerciseProgressionSection />
    </div>
  );
}

function ExerciseProgressionSection() {
  const [exercises, setExercises] = useState(null);
  const [selected, setSelected] = useState("");
  const [progPeriod, setProgPeriod] = useState("3months");
  const [progression, setProgression] = useState(null);
  const [progLoading, setProgLoading] = useState(false);
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
    let cancelled = false;
    setProgLoading(true);
    setProgError("");
    getExerciseProgression(selected, progPeriod)
      .then((p) => { if (!cancelled) setProgression(p); })
      .catch((err) => { if (!cancelled) setProgError(extractErrorMessage(err)); })
      .finally(() => { if (!cancelled) setProgLoading(false); });
    return () => { cancelled = true; };
  }, [selected, progPeriod]);

  if (exercises === null) {
    return progError ? (
      <div className="card"><ErrorBanner message={progError} /></div>
    ) : null; // still loading the picker -- avoid a flash of an empty section
  }
  if (exercises.length === 0) {
    return (
      <div className="card">
        <p style={{ fontWeight: 600, marginBottom: 4 }}>Progress</p>
        <EmptyState title="Log a few workouts to see your progression on specific exercises" />
      </div>
    );
  }

  const sessions = progression?.sessions || [];
  const first = sessions[0];
  const latest = sessions[sessions.length - 1];
  const change = sessions.length >= 2 ? round1(latest.top_weight - first.top_weight) : null;

  return (
    <div className="card">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10, flexWrap: "wrap", marginBottom: 2 }}>
        <p style={{ fontWeight: 600 }}>Progress</p>
        <SegmentedControl options={PROGRESSION_PERIODS} value={progPeriod} onChange={setProgPeriod} />
      </div>
      <p style={{ fontSize: 11, color: "var(--text-faint)", marginBottom: 10 }}>
        Your heaviest set each session
      </p>

      <select value={selected} onChange={(e) => setSelected(e.target.value)} style={{ marginBottom: 12 }}>
        {exercises.map((ex) => (
          <option key={ex.name} value={ex.name}>{ex.name}</option>
        ))}
      </select>

      <ErrorBanner message={progError} />

      {!progression && !progError && <Loading />}

      {progression && (
        <div style={{ opacity: progLoading ? 0.5 : 1, transition: "opacity 0.15s ease" }}>
          {sessions.length === 0 ? (
            <EmptyState title={`No ${selected} logged in this period`} />
          ) : (
            <>
              <ProgressionChart sessions={sessions} resetKey={`${selected}|${progPeriod}`} />
              <div style={{ display: "flex", justifyContent: "space-between", flexWrap: "wrap", gap: 8, marginTop: 10, fontSize: 12 }}>
                <span style={{ color: "var(--text-faint)" }}>
                  Latest: <strong style={{ color: "var(--text)" }}>{latest.top_weight} kg × {latest.top_weight_reps}</strong>
                </span>
                {change !== null && (
                  <span style={{ color: change > 0 ? "var(--bamboo)" : change < 0 ? "var(--chili)" : "var(--text-faint)" }}>
                    {change > 0 ? "↑" : change < 0 ? "↓" : "→"} {Math.abs(change)} kg since {shortDate(first.date)}
                  </span>
                )}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}

function ProgressionChart({ sessions, resetKey }) {
  const [ref, width] = useWidth();
  // The selection remembers which exercise/period it was made under, so
  // it's ignored (not just cleared later) once either one changes.
  const [sel, setSel] = useState({ key: resetKey, index: null });
  const a = sel.key === resetKey && sel.index !== null && sel.index < sessions.length ? sel.index : null;

  const height = width >= 560 ? 220 : 170;
  const pad = { top: 16, right: 16, bottom: 26, left: 56 };

  const weights = sessions.map((s) => s.top_weight);
  const times = sessions.map((s) => toTime(s.date));
  const lo = Math.min(...weights);
  const hi = Math.max(...weights);
  const span = hi - lo || Math.max(hi * 0.1, 1);
  const scaleMin = lo - span * 0.15;
  const scaleMax = hi + span * 0.15;
  const minT = Math.min(...times);
  const maxT = Math.max(...times);

  const plotW = Math.max(width - pad.left - pad.right, 1);
  const plotH = height - pad.top - pad.bottom;
  const baseY = pad.top + plotH;
  const xFor = (t) => (maxT === minT ? pad.left + plotW / 2 : pad.left + ((t - minT) / (maxT - minT)) * plotW);
  const yFor = (w) => pad.top + plotH - ((w - scaleMin) / (scaleMax - scaleMin)) * plotH;

  const pts = sessions.map((s) => [xFor(toTime(s.date)), yFor(s.top_weight)]);
  const line = pts.map(([x, y]) => `${x},${y}`).join(" ");
  const ticks = [0, 0.5, 1].map((t) => scaleMin + t * (scaleMax - scaleMin));
  const showAllDots = sessions.length <= 31;
  const last = pts[pts.length - 1];

  function pick(e) {
    const x = e.clientX - e.currentTarget.getBoundingClientRect().left;
    let best = 0;
    for (let i = 1; i < pts.length; i++) {
      if (Math.abs(pts[i][0] - x) < Math.abs(pts[best][0] - x)) best = i;
    }
    setSel({ key: resetKey, index: best });
  }

  return (
    <div ref={ref} style={{ width: "100%" }}>
      <div style={{ minHeight: 22, fontSize: 13, display: "flex", gap: 8, alignItems: "baseline", flexWrap: "wrap" }}>
        {a !== null && (
          <>
            <span style={{ color: "var(--text-faint)" }}>{fullDate(sessions[a].date)}</span>
            <strong className="stat">{sessions[a].top_weight} kg × {sessions[a].top_weight_reps}</strong>
            <span style={{ color: "var(--text-faint)" }}>{sessions[a].total_sets} sets</span>
          </>
        )}
      </div>

      {width > 0 && (
        <svg
          width={width}
          height={height}
          style={{ display: "block", touchAction: "pan-y" }}
          onPointerMove={pick}
          onPointerDown={pick}
          onPointerLeave={(e) => e.pointerType === "mouse" && setSel({ key: resetKey, index: null })}
        >
          {ticks.map((v) => (
            <g key={v}>
              <line x1={pad.left} x2={width - pad.right} y1={yFor(v)} y2={yFor(v)} stroke="var(--border-soft)" strokeWidth="1" />
              <text x={pad.left - 8} y={yFor(v) + 3} fontSize="10" fill="var(--text-faint)" textAnchor="end">
                {round1(v)} kg
              </text>
            </g>
          ))}

          {sessions.length > 1 && (
            <>
              <polygon points={`${pts[0][0]},${baseY} ${line} ${last[0]},${baseY}`} fill="var(--bamboo-tint)" />
              <polyline points={line} fill="none" stroke="var(--bamboo)" strokeWidth="2.5" strokeLinejoin="round" strokeLinecap="round" />
            </>
          )}

          {a !== null && (
            <line x1={pts[a][0]} x2={pts[a][0]} y1={pad.top} y2={baseY} stroke="var(--text-faint)" strokeWidth="1" opacity="0.5" />
          )}

          {sessions.map((s, i) =>
            showAllDots || i === sessions.length - 1 || i === a ? (
              <circle
                key={i}
                cx={pts[i][0]}
                cy={pts[i][1]}
                r={i === a ? 5 : i === sessions.length - 1 ? 4.5 : 3}
                fill="var(--bamboo)"
                stroke={i === a ? "var(--bg-card)" : "none"}
                strokeWidth="2"
              />
            ) : null
          )}

          {sessions.length === 1 ? (
            <text x={pad.left + plotW / 2} y={height - 6} fontSize="10" fill="var(--text-faint)" textAnchor="middle">
              {shortDate(sessions[0].date)}
            </text>
          ) : (
            <>
              <text x={pad.left} y={height - 6} fontSize="10" fill="var(--text-faint)">{shortDate(sessions[0].date)}</text>
              <text x={width - pad.right} y={height - 6} fontSize="10" fill="var(--text-faint)" textAnchor="end">
                {shortDate(sessions[sessions.length - 1].date)}
              </text>
            </>
          )}
        </svg>
      )}
    </div>
  );
}

function VolumeBarChart({ days, resetKey }) {
  const [sel, setSel] = useState({ key: resetKey, index: null });
  const a = sel.key === resetKey && sel.index !== null && sel.index < days.length ? sel.index : null;
  const maxValue = Math.max(...days.map((d) => d.volume), 1);
  const isMonth = days.length > 7;
  const gap = isMonth ? 2 : 6;
  const picked = a !== null ? days[a] : null;

  function pick(e) {
    const rect = e.currentTarget.getBoundingClientRect();
    const i = Math.floor(((e.clientX - rect.left) / rect.width) * days.length);
    setSel({ key: resetKey, index: Math.min(Math.max(i, 0), days.length - 1) });
  }

  return (
    <div>
      <div style={{ minHeight: 22, fontSize: 13, display: "flex", gap: 8, alignItems: "baseline", flexWrap: "wrap" }}>
        {picked && (
          <>
            <span style={{ color: "var(--text-faint)" }}>{dayLabel(picked.date)}</span>
            {picked.logged ? (
              <>
                <strong className="stat">{Math.round(picked.volume).toLocaleString()} kg</strong>
                <span style={{ color: "var(--text-faint)" }}>
                  {picked.workouts} {picked.workouts === 1 ? "workout" : "workouts"}
                </span>
              </>
            ) : (
              <span style={{ color: "var(--text-faint)" }}>No workout</span>
            )}
          </>
        )}
      </div>

      <div
        style={{ display: "flex", alignItems: "flex-end", gap, height: 120, touchAction: "pan-y" }}
        onPointerMove={pick}
        onPointerDown={pick}
        onPointerLeave={(e) => e.pointerType === "mouse" && setSel({ key: resetKey, index: null })}
      >
        {days.map((day, i) => {
          const pct = Math.min((day.volume / maxValue) * 100, 100);
          return (
            <div key={day.date} style={{ flex: 1, height: "100%", display: "flex", alignItems: "flex-end" }}>
              <div
                style={{
                  width: "100%",
                  height: `${pct}%`,
                  minHeight: day.logged ? 3 : 0,
                  borderRadius: 2,
                  background: day.logged ? "var(--bamboo)" : "var(--bg-raised)",
                  opacity: a !== null && a !== i ? 0.45 : 1,
                }}
              />
            </div>
          );
        })}
      </div>

      {isMonth ? (
        <div style={{ display: "flex", justifyContent: "space-between", marginTop: 4, fontSize: 10, color: "var(--text-faint)" }}>
          <span>{shortDate(days[0].date)}</span>
          <span>{shortDate(days[days.length - 1].date)}</span>
        </div>
      ) : (
        <div style={{ display: "flex", gap, marginTop: 4 }}>
          {days.map((day) => (
            <span key={day.date} style={{ flex: 1, textAlign: "center", fontSize: 9, color: "var(--text-faint)" }}>
              {weekdayLetter(day.date)}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function StatBox({ label, value }) {
  return (
    <div style={{ background: "var(--bg-raised)", borderRadius: "var(--radius-sm)", padding: "10px 4px" }}>
      <div className="stat" style={{ fontSize: 15 }}>{value}</div>
      <div className="eyebrow" style={{ marginTop: 4 }}>{label}</div>
    </div>
  );
}