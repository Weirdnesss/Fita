import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { formatWeight, formatWeightDelta } from "../../lib/profile";
import { useWidth } from "../../lib/useWidth";
import SegmentedControl from "../../components/SegmentedControl";
// [value, label, days]. Same toggle pattern as the nutrition/workout
// trends panels; "all" has no cutoff.
const PERIODS = [
  ["month", "30 Days", 30],
  ["3months", "3 Months", 90],
  ["all", "All Time", null],
];

// Which direction of weight change counts as "good" depends on the
// user's goal. Mirrors accounts.models.PrimaryGoal on the backend.
// maintain_weight / build_strength (or no goal) color neither direction.
function goalWeightDirection(primaryGoal) {
  if (primaryGoal === "lose_weight") return "down";
  if (primaryGoal === "gain_weight" || primaryGoal === "gain_muscle") return "up";
  return null;
}

// logged_at is a date-only string; adding a time keeps it in local time
// instead of UTC, which can shift the day in some timezones.
const toTime = (dateStr) => new Date(`${dateStr}T00:00:00`).getTime();
const shortDate = (dateStr) =>
  new Date(`${dateStr}T00:00:00`).toLocaleDateString(undefined, { month: "short", day: "numeric" });
const round1 = (n) => Math.round(n * 10) / 10;

export default function WeightChart({ logs, goalWeightKg, primaryGoal, unitSystem = "metric" }) {
  const [period, setPeriod] = useState("month");

  if (!logs?.length) return null;

  // `logs` arrives most-recent-first.
  const days = PERIODS.find(([v]) => v === period)[2];
  const cutoff = days ? Date.now() - days * 86400000 : null;
  const inPeriod = [...logs].reverse().filter((e) => cutoff === null || toTime(e.logged_at) >= cutoff);

  const change =
    inPeriod.length > 1 ? round1(inPeriod[inPeriod.length - 1].weight_kg - inPeriod[0].weight_kg) : null;
  const changeDelta = change !== null ? formatWeightDelta(change, unitSystem) : null;
  const direction = goalWeightDirection(primaryGoal);
  const isGood = !change ? null : direction === "down" ? change < 0 : direction === "up" ? change > 0 : null;
  const changeColor = isGood === null ? "var(--text)" : isGood ? "var(--bamboo)" : "var(--chili)";
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
        <span style={{ fontSize: 13, color: "var(--text-dim)" }}>
          Change:{" "}
          <strong className="stat" style={{ color: changeColor }}>
            {changeDelta ? `${changeDelta.value > 0 ? "+" : ""}${changeDelta.value} ${changeDelta.unit}` : "--"}
          </strong>
        </span>
        <SegmentedControl options={PERIODS.map(([v, label]) => [v, label])} value={period} onChange={setPeriod} />
      </div>

      {inPeriod.length === 0 ? (
        <p style={{ fontSize: 13, color: "var(--text-faint)", textAlign: "center", padding: "16px 0" }}>
          No entries in this period. Try a longer range.
        </p>
      ) : (
        <Chart period={period} data={inPeriod} goalWeightKg={goalWeightKg} unitSystem={unitSystem} />
      )}
    </div>
  );
}

const fullDate = (dateStr) =>
  new Date(`${dateStr}T00:00:00`).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });

function Chart({ period, data, goalWeightKg, unitSystem }) {
  const [ref, width] = useWidth();
  const [active, setActive] = useState(null);
  
  useEffect(() => {
    setActive(null);
  }, [period]);
  
  const height = width >= 560 ? 240 : 180;
  const pad = { top: 18, right: 16, bottom: 26, left: 56 };

  const weights = data.map((e) => e.weight_kg);
  const times = data.map((e) => toTime(e.logged_at));
  let lo = Math.min(...weights);
  let hi = Math.max(...weights);
  if (goalWeightKg != null) {
    lo = Math.min(lo, goalWeightKg);
    hi = Math.max(hi, goalWeightKg);
  }
  const span = hi - lo || 1;
  const scaleMin = lo - span * 0.12;
  const scaleMax = hi + span * 0.12;
  const minT = Math.min(...times);
  const maxT = Math.max(...times);

  const plotW = Math.max(width - pad.left - pad.right, 1);
  const plotH = height - pad.top - pad.bottom;
  const baseY = pad.top + plotH;
  const xFor = (t) => (maxT === minT ? pad.left + plotW / 2 : pad.left + ((t - minT) / (maxT - minT)) * plotW);
  const yFor = (w) => pad.top + plotH - ((w - scaleMin) / (scaleMax - scaleMin)) * plotH;

  const pts = data.map((e) => [xFor(toTime(e.logged_at)), yFor(e.weight_kg)]);
  const line = pts.map(([x, y]) => `${x},${y}`).join(" ");
  const ticks = [0, 0.5, 1].map((t) => scaleMin + t * (scaleMax - scaleMin));
  const showAllDots = data.length <= 31;
  const last = pts[pts.length - 1];

  // guard against a stale index if the data shrinks (e.g. period change)
  const a = active !== null && active < data.length ? active : null;

  function pick(e) {
    const x = e.clientX - e.currentTarget.getBoundingClientRect().left;
    let best = 0;
    for (let i = 1; i < pts.length; i++) {
      if (Math.abs(pts[i][0] - x) < Math.abs(pts[best][0] - x)) best = i;
    }
    setActive(best);
  }

  return (
    <div ref={ref} style={{ width: "100%" }}>
      <div style={{ minHeight: 22, fontSize: 13, display: "flex", gap: 8, alignItems: "baseline" }}>
        {a !== null && (
          <>
            <span style={{ color: "var(--text-faint)" }}>{fullDate(data[a].logged_at)}</span>
            <strong className="stat">{formatWeight(data[a].weight_kg, unitSystem)}</strong>
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
          onPointerLeave={(e) => e.pointerType === "mouse" && setActive(null)}
        >
          {ticks.map((v) => (
            <g key={v}>
              <line x1={pad.left} x2={width - pad.right} y1={yFor(v)} y2={yFor(v)} stroke="var(--border-soft)" strokeWidth="1" />
              <text x={pad.left - 8} y={yFor(v) + 3} fontSize="10" fill="var(--text-faint)" textAnchor="end">
                {formatWeight(round1(v), unitSystem)}
              </text>
            </g>
          ))}

          {goalWeightKg != null && (
            <line
              x1={pad.left} x2={width - pad.right}
              y1={yFor(goalWeightKg)} y2={yFor(goalWeightKg)}
              stroke="var(--turmeric)" strokeWidth="1.5" strokeDasharray="4 3" opacity="0.7"
            />
          )}

          {data.length > 1 && (
            <>
              <polygon points={`${pts[0][0]},${baseY} ${line} ${last[0]},${baseY}`} fill="var(--bamboo-tint)" />
              <polyline points={line} fill="none" stroke="var(--bamboo)" strokeWidth="2.5" strokeLinejoin="round" strokeLinecap="round" />
            </>
          )}

          {a !== null && (
            <line x1={pts[a][0]} x2={pts[a][0]} y1={pad.top} y2={baseY} stroke="var(--text-faint)" strokeWidth="1" opacity="0.5" />
          )}

          {data.map((e, i) =>
            showAllDots || i === data.length - 1 || i === a ? (
              <circle
                key={e.id}
                cx={pts[i][0]}
                cy={pts[i][1]}
                r={i === a ? 5 : i === data.length - 1 ? 4.5 : 3}
                fill="var(--bamboo)"
                stroke={i === a ? "var(--bg-card)" : "none"}
                strokeWidth="2"
              />
            ) : null
          )}

          {data.length === 1 ? (
            <text x={pad.left + plotW / 2} y={height - 6} fontSize="10" fill="var(--text-faint)" textAnchor="middle">
              {shortDate(data[0].logged_at)}
            </text>
          ) : (
            <>
              <text x={pad.left} y={height - 6} fontSize="10" fill="var(--text-faint)">{shortDate(data[0].logged_at)}</text>
              <text x={width - pad.right} y={height - 6} fontSize="10" fill="var(--text-faint)" textAnchor="end">
                {shortDate(data[data.length - 1].logged_at)}
              </text>
            </>
          )}
        </svg>
      )}
    </div>
  );
}