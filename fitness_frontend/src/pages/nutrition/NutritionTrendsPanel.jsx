import { useEffect, useState } from "react";
import { Loading, ErrorBanner, extractErrorMessage } from "../../components/Status";
import { getNutritionTrends, getNutritionProfile } from "../../api/nutrition";
import SegmentedControl from "../../components/SegmentedControl";

const PERIODS = [
  ["week", "This Week"],
  ["month", "This Month"],
];

// date-only strings need a time added or some timezones show the day before
const parse = (s) => new Date(`${s}T00:00:00`);
const shortDate = (s) => parse(s).toLocaleDateString(undefined, { month: "short", day: "numeric" });
const dayLabel = (s) => parse(s).toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" });
const weekdayLetter = (s) => parse(s).toLocaleDateString(undefined, { weekday: "narrow" });

export default function NutritionTrendsPanel() {
  const [period, setPeriod] = useState("week");
  const [trends, setTrends] = useState(null);
  const [loading, setLoading] = useState(true);
  const [goals, setGoals] = useState(null);
  const [error, setError] = useState("");

  // Goals don't depend on the period, so fetch them once. A failure here
  // only removes the goal line/labels -- it shouldn't block the trends.
  useEffect(() => {
    getNutritionProfile().then(setGoals).catch(() => {});
  }, []);

  // Old data stays on screen (dimmed) while the next period loads, so
  // switching doesn't blank and remount the whole panel.
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError("");
    getNutritionTrends(period)
      .then((t) => { if (!cancelled) setTrends(t); })
      .catch((err) => { if (!cancelled) setError(extractErrorMessage(err)); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [period]);

  const goal = goals?.daily_calories_goal || 0;

  return (
    <div className="nutrition-trends" style={{ display: "flex", flexDirection: "column", gap: 16 }}>
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
              <div className="stat" style={{ fontSize: 20 }}>{trends.days_logged}/{trends.days.length}</div>
              <div className="eyebrow">Days Logged</div>
            </div>
          </div>

          {trends.days_logged === 0 ? (
            <div className="card" style={{ textAlign: "center" }}>
              <p style={{ fontSize: 13, color: "var(--text-faint)" }}>
                No food logged yet {period === "week" ? "this week" : "this month"} -- log a
                few days to see your trends.
              </p>
            </div>
          ) : (
            <>
              <div className="card">
                <p style={{ fontWeight: 600, marginBottom: 10 }}>Calories</p>
                <CalorieBarChart days={trends.days} goal={goal} resetKey={period} />
              </div>

              <div className="card">
                <p style={{ fontWeight: 600, marginBottom: 10 }}>
                  Averages <span style={{ fontWeight: 400, fontSize: 12, color: "var(--text-faint)" }}>(on logged days)</span>
                </p>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 8, textAlign: "center" }}>
                  <MacroBox label="Calories" value={Math.round(trends.averages.calories)} goal={goals?.daily_calories_goal} accent="chili" />
                  <MacroBox label="Protein" value={Math.round(trends.averages.protein_g)} unit="g" goal={goals?.daily_protein_goal} accent="bamboo" />
                  <MacroBox label="Carbs" value={Math.round(trends.averages.carbs_g)} unit="g" goal={goals?.daily_carbs_goal} accent="turmeric" />
                  <MacroBox label="Fat" value={Math.round(trends.averages.fat_g)} unit="g" goal={goals?.daily_fat_goal} accent="ube" />
                </div>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}

function CalorieBarChart({ days, goal, resetKey }) {
  // The selection remembers which period it was made under, so it's
  // ignored (not just cleared later) once the period changes.
  const [sel, setSel] = useState({ key: resetKey, index: null });
  const a = sel.key === resetKey && sel.index !== null && sel.index < days.length ? sel.index : null;
  const picked = a !== null ? days[a] : null;

  const maxValue = Math.max(goal || 0, ...days.map((d) => d.calories), 1);
  const isMonth = days.length > 7;
  const gap = isMonth ? 2 : 6;

  function pick(e) {
    const rect = e.currentTarget.getBoundingClientRect();
    const i = Math.floor(((e.clientX - rect.left) / rect.width) * days.length);
    setSel({ key: resetKey, index: Math.min(Math.max(i, 0), days.length - 1) });
  }

  const diff = picked && picked.logged && goal ? Math.round(picked.calories - goal) : null;

  return (
    <div>
      <div style={{ minHeight: 22, fontSize: 13, display: "flex", gap: 8, alignItems: "baseline", flexWrap: "wrap" }}>
        {picked && (
          <>
            <span style={{ color: "var(--text-faint)" }}>{dayLabel(picked.date)}</span>
            {picked.logged ? (
              <>
                <strong className="stat">{Math.round(picked.calories).toLocaleString()} kcal</strong>
                {diff !== null && (
                  <span style={{ color: diff > 0 ? "var(--chili)" : "var(--text-faint)" }}>
                    {diff > 0 ? `${diff} over` : `${Math.abs(diff)} under`}
                  </span>
                )}
              </>
            ) : (
              <span style={{ color: "var(--text-faint)" }}>Not logged</span>
            )}
          </>
        )}
      </div>

      <div style={{ position: "relative", height: 120 }}>
        <div
          style={{ display: "flex", alignItems: "flex-end", gap, height: "100%", touchAction: "pan-y" }}
          onPointerMove={pick}
          onPointerDown={pick}
          onPointerLeave={(e) => e.pointerType === "mouse" && setSel({ key: resetKey, index: null })}
        >
          {days.map((d, i) => {
            const pct = Math.min((d.calories / maxValue) * 100, 100);
            const isOver = goal && d.calories > goal;
            return (
              <div key={d.date} style={{ flex: 1, height: "100%", display: "flex", alignItems: "flex-end" }}>
                <div
                  style={{
                    width: "100%",
                    height: `${pct}%`,
                    minHeight: d.logged ? 3 : 0,
                    borderRadius: 2,
                    background: !d.logged ? "var(--bg-raised)" : isOver ? "var(--chili)" : "var(--bamboo)",
                    opacity: a !== null && a !== i ? 0.45 : 1,
                  }}
                />
              </div>
            );
          })}
        </div>

        {goal > 0 && (
          <div
            style={{
              position: "absolute",
              left: 0,
              right: 0,
              bottom: `${(goal / maxValue) * 100}%`,
              borderTop: "1.5px dashed var(--turmeric)",
              opacity: 0.7,
              pointerEvents: "none",
            }}
          />
        )}
      </div>

      {isMonth ? (
        <div style={{ display: "flex", justifyContent: "space-between", marginTop: 4, fontSize: 10, color: "var(--text-faint)" }}>
          <span>{shortDate(days[0].date)}</span>
          <span>{shortDate(days[days.length - 1].date)}</span>
        </div>
      ) : (
        <div style={{ display: "flex", gap, marginTop: 4 }}>
          {days.map((d) => (
            <span key={d.date} style={{ flex: 1, textAlign: "center", fontSize: 9, color: "var(--text-faint)" }}>
              {weekdayLetter(d.date)}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function MacroBox({ label, value, unit = "", goal, accent }) {
  return (
    <div style={{ background: "var(--bg-raised)", borderRadius: "var(--radius-sm)", padding: "10px 4px" }}>
      <div className="stat" style={{ fontSize: 15, color: `var(--${accent})` }}>{value}{unit}</div>
      <div className="eyebrow" style={{ marginTop: 4 }}>{label}</div>
      {goal ? (
        <div style={{ fontSize: 10, color: "var(--text-faint)", marginTop: 2 }}>
          goal {Math.round(goal)}{unit}
        </div>
      ) : null}
    </div>
  );
}