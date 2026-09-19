import { formatWeight, formatWeightDelta } from "../../lib/profile";

// Lightweight hand-rolled SVG line chart -- no charting library is
// installed in this project, and adding one for a single chart felt
// like overkill. Plots logged_at (x) against weight_kg (y), with an
// optional dashed reference line for goal weight. `logs` comes in
// most-recent-first (the API's default ordering), so it's reversed
// here to plot left-to-right chronologically.
// Which direction of weight change counts as "good" depends on the
// user's actual goal -- losing weight is progress for lose_weight, but
// it's the opposite of progress for gain_weight/gain_muscle. Mirrors
// accounts.models.PrimaryGoal on the backend. maintain_weight and
// build_strength aren't about weight direction at all, so neither
// direction is colored as good/bad for those (or if the goal isn't set).
function goalWeightDirection(primaryGoal) {
  if (primaryGoal === "lose_weight") return "down";
  if (primaryGoal === "gain_weight" || primaryGoal === "gain_muscle") return "up";
  return null;
}

export default function WeightChart({ logs, goalWeightKg, primaryGoal, unitSystem = "metric" }) {
  const width = 320;
  const height = 150;
  const padding = { top: 14, right: 14, bottom: 20, left: 14 };

  const chronological = [...logs].reverse();
  const weights = chronological.map((e) => e.weight_kg);
  const times = chronological.map((e) => new Date(e.logged_at).getTime());

  const dataMin = Math.min(...weights);
  const dataMax = Math.max(...weights);
  let scaleMin = goalWeightKg != null ? Math.min(dataMin, goalWeightKg) : dataMin;
  let scaleMax = goalWeightKg != null ? Math.max(dataMax, goalWeightKg) : dataMax;
  const span = scaleMax - scaleMin || 1;
  scaleMin -= span * 0.12;
  scaleMax += span * 0.12;

  const minTime = Math.min(...times);
  const maxTime = Math.max(...times);
  const timeSpan = maxTime - minTime || 1;

  const plotWidth = width - padding.left - padding.right;
  const plotHeight = height - padding.top - padding.bottom;

  const xFor = (t) => padding.left + ((t - minTime) / timeSpan) * plotWidth;
  const yFor = (w) => padding.top + plotHeight - ((w - scaleMin) / (scaleMax - scaleMin)) * plotHeight;

  const points = chronological.map((e) => `${xFor(new Date(e.logged_at).getTime())},${yFor(e.weight_kg)}`).join(" ");
  const latest = chronological[chronological.length - 1];
  const first = chronological[0];
  const change = Math.round((latest.weight_kg - first.weight_kg) * 10) / 10;
  const changeDelta = formatWeightDelta(change, unitSystem);
  const direction = goalWeightDirection(primaryGoal);
  const isGoodChange = change === 0 ? null : direction === "down" ? change < 0 : direction === "up" ? change > 0 : null;
  const changeColor = isGoodChange === null ? "var(--text)" : isGoodChange ? "var(--bamboo)" : "var(--chili)";

  return (
    <div>
      <svg viewBox={`0 0 ${width} ${height}`} style={{ width: "100%", height: "auto", display: "block" }}>
        {goalWeightKg != null && (
          <line
            x1={padding.left} x2={width - padding.right}
            y1={yFor(goalWeightKg)} y2={yFor(goalWeightKg)}
            stroke="var(--turmeric)" strokeWidth="1.5" strokeDasharray="4 3"
          />
        )}
        <polyline points={points} fill="none" stroke="var(--bamboo)" strokeWidth="2.5" strokeLinejoin="round" strokeLinecap="round" />
        {chronological.map((e) => (
          <circle key={e.id} cx={xFor(new Date(e.logged_at).getTime())} cy={yFor(e.weight_kg)} r="3" fill="var(--bamboo)" />
        ))}
        <text x={padding.left} y={height - 4} fontSize="9" fill="var(--text-faint)">{first.logged_at}</text>
        <text x={width - padding.right} y={height - 4} fontSize="9" fill="var(--text-faint)" textAnchor="end">{latest.logged_at}</text>
      </svg>
      <div style={{ display: "flex", justifyContent: "space-between", marginTop: 8, fontSize: 12, color: "var(--text-faint)" }}>
        <span>Latest: <strong style={{ color: "var(--text)" }}>{formatWeight(latest.weight_kg, unitSystem)}</strong></span>
        <span>
          Change: <strong style={{ color: changeColor }}>
            {changeDelta.value > 0 ? "+" : ""}{changeDelta.value} {changeDelta.unit}
          </strong>
        </span>
        {goalWeightKg != null && <span>Goal: <strong style={{ color: "var(--turmeric)" }}>{formatWeight(goalWeightKg, unitSystem)}</strong></span>}
      </div>
    </div>
  );
}
