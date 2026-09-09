import { useEffect, useState } from "react";
import PageHeader from "../../components/PageHeader";
import { Loading, ErrorBanner, extractErrorMessage } from "../../components/Status";
import { getNutritionTrends, getNutritionProfile } from "../../api/nutrition";

const PERIODS = [
  ["week", "This Week"],
  ["month", "This Month"],
];

export default function NutritionTrends() {
  const [period, setPeriod] = useState("week");
  const [trends, setTrends] = useState(null);
  const [goals, setGoals] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    setTrends(null);
    setError("");
    Promise.all([getNutritionTrends(period), getNutritionProfile()])
      .then(([t, g]) => {
        setTrends(t);
        setGoals(g);
      })
      .catch((err) => setError(extractErrorMessage(err)));
  }, [period]);

  return (
    <div className="page">
      <PageHeader title="Trends" subtitle="Your logging patterns over time" back />
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
                <CalorieBarChart days={trends.days} goal={goals?.daily_calories_goal} />
              </div>

              <div className="card">
                <p style={{ fontWeight: 600, marginBottom: 10 }}>
                  Averages <span style={{ fontWeight: 400, fontSize: 12, color: "var(--text-faint)" }}>(on logged days)</span>
                </p>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 8, textAlign: "center" }}>
                  <MacroBox label="Calories" value={Math.round(trends.averages.calories)} />
                  <MacroBox label="Protein" value={`${Math.round(trends.averages.protein_g)}g`} />
                  <MacroBox label="Carbs" value={`${Math.round(trends.averages.carbs_g)}g`} />
                  <MacroBox label="Fat" value={`${Math.round(trends.averages.fat_g)}g`} />
                </div>
              </div>
            </>
          )}
        </>
      )}
    </div>
  );
}

function CalorieBarChart({ days, goal }) {
  const maxValue = Math.max(goal || 0, ...days.map((d) => d.calories), 1);
  const isMonth = days.length > 7;
  return (
    <div style={{ display: "flex", alignItems: "flex-end", gap: isMonth ? 2 : 6, height: 120 }}>
      {days.map((d) => {
        const pct = Math.min((d.calories / maxValue) * 100, 100);
        const isOver = goal && d.calories > goal;
        return (
          <div key={d.date} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", height: "100%", justifyContent: "flex-end", gap: 4 }}>
            <div
              style={{
                width: "100%",
                height: `${pct}%`,
                minHeight: d.logged ? 3 : 0,
                borderRadius: 2,
                background: !d.logged ? "var(--bg-raised)" : isOver ? "var(--chili)" : "var(--bamboo)",
              }}
              title={`${formatShortDate(d.date)}: ${Math.round(d.calories)} kcal`}
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

function MacroBox({ label, value }) {
  return (
    <div style={{ background: "var(--bg-raised)", borderRadius: "var(--radius-sm)", padding: "10px 4px" }}>
      <div className="stat" style={{ fontSize: 15 }}>{value}</div>
      <div className="eyebrow" style={{ marginTop: 4 }}>{label}</div>
    </div>
  );
}