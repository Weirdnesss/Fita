import { createContext, useContext } from "react";
import { useRestTimer } from "../components/RestTimer";

// One rest timer for the whole app. It used to live inside ActiveWorkout, so leaving
// the page stopped the countdown and its "rest over" alert. Here it keeps running,
// and the floating workout pill can show and control it.
const RestTimerContext = createContext(null);

export function RestTimerProvider({ children }) {
  const timer = useRestTimer();
  return <RestTimerContext.Provider value={timer}>{children}</RestTimerContext.Provider>;
}

export function useSharedRestTimer() {
  const timer = useContext(RestTimerContext);
  if (!timer) throw new Error("useSharedRestTimer must be used inside RestTimerProvider");
  return timer;
}
