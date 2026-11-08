import { useEffect, useState } from "react";

// The workout the user has started but not finished: { templateId, title, startedAt }.
// It lives in localStorage next to the logged sets (see ActiveWorkout), so the two
// always exist together and survive the app being closed or killed mid-workout. Everything that needs to know "is a workout in progress?"
// (the floating pill, the start buttons, the page guard) reads it from here.
const KEY = "fita_active_workout";
const EVENT = "fita-active-workout-change";

// Where ActiveWorkout keeps the logged sets for one routine.
export function workoutSessionKey(templateId) {
  return `active_workout_${templateId}`;
}

export function getActiveWorkout() {
  try {
    const saved = JSON.parse(localStorage.getItem(KEY));
    if (saved && saved.templateId != null && saved.startedAt) return saved;
  } catch {
    /* missing or unreadable -- treat as no workout in progress */
  }
  return null;
}

export function setActiveWorkout(workout) {
  try {
    localStorage.setItem(KEY, JSON.stringify(workout));
  } catch {
    /* storage unavailable -- the workout still works, it just can't be minimized */
  }
  window.dispatchEvent(new Event(EVENT));
}

// Pass the template id to only clear that workout's marker.
export function clearActiveWorkout(templateId) {
  const current = getActiveWorkout();
  if (templateId !== undefined && current && String(current.templateId) !== String(templateId)) return;
  try {
    // Clearing with no id (logout) must also drop the saved sets, or the next
    // person using this browser would find them.
    if (current && templateId === undefined) localStorage.removeItem(workoutSessionKey(current.templateId));
    localStorage.removeItem(KEY);
  } catch {
    /* ignore */
  }
  window.dispatchEvent(new Event(EVENT));
}

export function useActiveWorkout() {
  const [active, setActive] = useState(getActiveWorkout);
  useEffect(() => {
    const sync = () => setActive(getActiveWorkout());
    // "storage" fires when another tab changes it, so every open tab stays in step.
    const onStorage = (e) => (e.key === KEY || e.key === null) && sync();
    window.addEventListener(EVENT, sync);
    window.addEventListener("storage", onStorage);
    sync();
    return () => {
      window.removeEventListener(EVENT, sync);
      window.removeEventListener("storage", onStorage);
    };
  }, []);
  return active;
}

export function formatElapsed(totalSeconds) {
  const h = Math.floor(totalSeconds / 3600);
  const m = Math.floor((totalSeconds % 3600) / 60);
  const s = totalSeconds % 60;
  const pad = (n) => String(n).padStart(2, "0");
  return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${m}:${pad(s)}`;
}
