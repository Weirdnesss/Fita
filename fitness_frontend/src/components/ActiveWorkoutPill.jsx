import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useActiveWorkout, formatElapsed } from "../lib/activeWorkout";
import { useSharedRestTimer } from "../context/RestTimerContext";
import { formatClock } from "./RestTimer";

const HIDDEN_ON = ["/login", "/signup", "/onboarding"];
const btn = { padding: "6px 10px", fontSize: 12, height: "auto", minHeight: 0 };

/**
 * Floating "workout in progress" card, shown on every page except the workout itself.
 * Tap the name to go back; while resting it also shows the countdown with -15s / +15s / Skip.
 */
export default function ActiveWorkoutPill() {
  const active = useActiveWorkout();
  const { running, finished, remaining, adjust, stop, dismiss } = useSharedRestTimer();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const [elapsed, setElapsed] = useState(0);
  const startedAt = active?.startedAt;

  useEffect(() => {
    if (!startedAt) return;
    const startMs = new Date(startedAt).getTime();
    const tick = () => setElapsed(Math.max(0, Math.floor((Date.now() - startMs) / 1000)));
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [startedAt]);

  const target = active ? `/workouts/templates/${active.templateId}/start` : null;
  if (!active || pathname === target || HIDDEN_ON.includes(pathname)) return null;

  const resting = running || finished;

  return (
    <div
      role="region"
      aria-label="Workout in progress"
      style={{
        position: "fixed",
        right: 12,
        bottom: "calc(var(--nav-height, 0px) + 12px)",
        zIndex: 20,
        width: "min(340px, calc(100vw - 24px))",
        background: "var(--bg-raised)",
        border: `2px solid var(--${resting ? "chili" : "bamboo"})`,
        borderRadius: 14,
        boxShadow: "0 6px 24px rgba(0, 0, 0, 0.45)",
        padding: "8px 12px",
      }}
    >
      <button
        onClick={() => navigate(target)}
        aria-label={`Return to ${active.title}`}
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 10,
          width: "100%",
          padding: 0,
          background: "none",
          border: "none",
          color: "inherit",
          textAlign: "left",
        }}
      >
        <span style={{ minWidth: 0 }}>
          <span className="eyebrow" style={{ display: "block" }}>Workout in progress</span>
          <span style={{ display: "block", fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {active.title}
          </span>
        </span>
        <span className="stat" style={{ fontSize: 18, flexShrink: 0 }}>{formatElapsed(elapsed)}</span>
      </button>

      {running && (
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8, marginTop: 8 }}>
          <span style={{ display: "flex", alignItems: "baseline", gap: 6 }}>
            <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: 1, color: "var(--text-dim)" }}>REST</span>
            <span className="stat" style={{ fontSize: 22, color: remaining <= 10 ? "var(--turmeric)" : "var(--text)" }}>
              {formatClock(remaining)}
            </span>
          </span>
          <span style={{ display: "flex", gap: 6 }}>
            <button className="btn btn-secondary" style={btn} onClick={() => adjust(-15)}>−15s</button>
            <button className="btn btn-secondary" style={btn} onClick={() => adjust(15)}>+15s</button>
            <button className="btn btn-primary" style={btn} onClick={stop}>Skip</button>
          </span>
        </div>
      )}

      {finished && (
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8, marginTop: 8 }}>
          <span style={{ fontWeight: 700, color: "var(--chili)" }}>Rest over: next set!</span>
          <button className="btn btn-primary" style={btn} onClick={dismiss}>Done</button>
        </div>
      )}
    </div>
  );
}
