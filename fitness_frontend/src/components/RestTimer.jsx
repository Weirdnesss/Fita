import { useCallback, useEffect, useRef, useState } from "react";

const RUN_KEY = "fita_rest_timer_run";
const DURATION_KEY = "fita_rest_timer_duration";
const DEFAULT_SECONDS = 90;
const MIN_SECONDS = 5;
const MAX_SECONDS = 600;
const PRESETS = [60, 90, 120, 180];
const AUTOSTART_KEY = "fita_rest_timer_autostart"; // "0" = off; anything else (or unset) = on

function readStorage(key) {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeStorage(key, value) {
  try {
    if (value === null) localStorage.removeItem(key);
    else localStorage.setItem(key, value);
  } catch {
    /* storage unavailable -- the timer still works, it just won't survive a reload */
  }
}

export function formatClock(totalSeconds) {
  const m = Math.floor(totalSeconds / 60);
  const s = totalSeconds % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

function loadRun() {
  try {
    const saved = JSON.parse(readStorage(RUN_KEY));
    if (saved && saved.endAt > Date.now() && saved.total > 0) return saved;
  } catch {
    /* corrupted value -- ignore */
  }
  return null;
}

/**
 * Rest timer state. Counts down against an absolute end time rather than
 * decrementing a counter, because phones throttle or suspend JS timers when
 * the screen locks or the app is backgrounded -- an absolute end time stays
 * correct no matter how often the interval actually fires.
 */
export function useRestTimer() {
  const [duration, setDuration] = useState(() => {
    const saved = parseInt(readStorage(DURATION_KEY), 10);
    return saved >= MIN_SECONDS && saved <= MAX_SECONDS ? saved : DEFAULT_SECONDS;
  });
  const [autoStart, setAutoStartState] = useState(() => readStorage(AUTOSTART_KEY) !== "0");
  const [run, setRun] = useState(loadRun); // { endAt, total } | null
  const [now, setNow] = useState(() => Date.now());
  const [finished, setFinished] = useState(false);
  const audioRef = useRef(null);
  const wakeLockRef = useRef(null);

  const remaining = run ? Math.max(0, Math.ceil((run.endAt - now) / 1000)) : 0;

  // -- alerts ---------------------------------------------------------

  const unlockAudio = useCallback(() => {
    // Must run inside a user gesture (the start tap) or mobile browsers
    // keep the AudioContext suspended and the beep never plays.
    try {
      if (!audioRef.current) {
        const Ctx = window.AudioContext || window.webkitAudioContext;
        if (Ctx) audioRef.current = new Ctx();
      }
      audioRef.current?.resume?.();
    } catch {
      /* no audio support -- vibration/visual alert still work */
    }
  }, []);

  const playBeeps = useCallback(() => {
    const ctx = audioRef.current;
    if (!ctx) return;
    try {
      if (ctx.state === "suspended") ctx.resume?.();
      [0, 0.25, 0.5].forEach((offset) => {
        const t = ctx.currentTime + offset;
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.type = "sine";
        osc.frequency.value = 880;
        gain.gain.setValueAtTime(0.0001, t);
        gain.gain.exponentialRampToValueAtTime(0.3, t + 0.02);
        gain.gain.exponentialRampToValueAtTime(0.0001, t + 0.2);
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.start(t);
        osc.stop(t + 0.22);
      });
    } catch {
      /* ignore */
    }
  }, []);

  const requestNotificationPermission = useCallback(() => {
    try {
      if ("Notification" in window && Notification.permission === "default") {
        Notification.requestPermission();
      }
    } catch {
      /* ignore */
    }
  }, []);

  const notifyDone = useCallback(() => {
    try {
      if (!("Notification" in window) || Notification.permission !== "granted" || !document.hidden) return;
      const options = { body: "Time for your next set.", tag: "fita-rest" };
      if (navigator.serviceWorker?.controller) {
        navigator.serviceWorker.ready
          .then((reg) => reg.showNotification("Rest over", options))
          .catch(() => {});
      } else {
        new Notification("Rest over", options);
      }
    } catch {
      /* ignore */
    }
  }, []);

  const alertDone = useCallback(() => {
    try {
      navigator.vibrate?.([250, 120, 250, 120, 500]); // Android; not supported on iOS
    } catch {
      /* ignore */
    }
    playBeeps();
    notifyDone();
  }, [playBeeps, notifyDone]);

  // -- keep the screen awake while resting ------------------------------

  const acquireWakeLock = useCallback(async () => {
    try {
      if (!("wakeLock" in navigator) || wakeLockRef.current || document.hidden) return;
      const lock = await navigator.wakeLock.request("screen");
      wakeLockRef.current = lock;
      lock.addEventListener("release", () => {
        if (wakeLockRef.current === lock) wakeLockRef.current = null;
      });
    } catch {
      wakeLockRef.current = null;
    }
  }, []);

  const releaseWakeLock = useCallback(() => {
    try {
      wakeLockRef.current?.release();
    } catch {
      /* ignore */
    }
    wakeLockRef.current = null;
  }, []);

  // -- effects ----------------------------------------------------------

  // Tick while running.
  useEffect(() => {
    if (!run) return;
    const id = setInterval(() => setNow(Date.now()), 250);
    return () => clearInterval(id);
  }, [run]);

  // Persist the run so a reload or a killed PWA tab doesn't lose it.
  useEffect(() => {
    writeStorage(RUN_KEY, run ? JSON.stringify(run) : null);
  }, [run]);

  // Finish when the end time passes.
  useEffect(() => {
    if (!run || now < run.endAt) return;
    setRun(null);
    setFinished(true);
    releaseWakeLock();
    alertDone();
  }, [run, now, releaseWakeLock, alertDone]);

  // Coming back to the app: re-sync immediately (don't wait for the next
  // tick) and re-take the wake lock, which browsers drop when hidden.
  useEffect(() => {
    function onVisibility() {
      setNow(Date.now());
      if (!document.hidden && run) acquireWakeLock();
    }
    document.addEventListener("visibilitychange", onVisibility);
    return () => document.removeEventListener("visibilitychange", onVisibility);
  }, [run, acquireWakeLock]);

  // A timer restored after a reload should keep the screen awake too;
  // always release on unmount.
  useEffect(() => {
    if (run) acquireWakeLock();
    return () => releaseWakeLock();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // -- controls ---------------------------------------------------------

  const start = useCallback(
    (seconds) => {
      const total = Math.max(MIN_SECONDS, Math.min(Math.round(seconds) || DEFAULT_SECONDS, MAX_SECONDS));
      unlockAudio();
      requestNotificationPermission();
      const t = Date.now();
      setRun({ endAt: t + total * 1000, total });
      setNow(t);
      setFinished(false);
      setDuration(total);
      writeStorage(DURATION_KEY, String(total));
      acquireWakeLock();
    },
    [unlockAudio, requestNotificationPermission, acquireWakeLock]
  );

  const adjust = useCallback((deltaSeconds) => {
    setRun((prev) => {
      if (!prev) return prev;
      return {
        endAt: Math.max(Date.now() + 1000, prev.endAt + deltaSeconds * 1000),
        total: Math.max(MIN_SECONDS, prev.total + deltaSeconds),
      };
    });
  }, []);

  const stop = useCallback(() => {
    setRun(null);
    setFinished(false);
    releaseWakeLock();
  }, [releaseWakeLock]);

  const dismiss = useCallback(() => setFinished(false), []);

  const setAutoStart = useCallback((on) => {
    setAutoStartState(on);
    writeStorage(AUTOSTART_KEY, on ? "1" : "0");
  }, []);

  return {
    running: run !== null,
    finished,
    remaining,
    total: run?.total ?? 0,
    duration,
    autoStart,
    setAutoStart,
    start,
    adjust,
    stop,
    dismiss,
  };
}

/** The visible timer card. Pass it the object returned by useRestTimer(). */
export default function RestTimer({ timer }) {
  const { running, finished, remaining, total, duration, autoStart, setAutoStart, start, adjust, stop, dismiss } = timer;
  const progress = running && total > 0 ? Math.max(0, Math.min(100, ((total - remaining) / total) * 100)) : 0;
  const almostDone = running && remaining <= 10;

  // Countdown in the browser tab title too, so it's visible on PC while
  // working in another tab. Cleanup restores the real title each tick.
  useEffect(() => {
    if (!running) return;
    const original = document.title;
    document.title = `${formatClock(remaining)} · Rest`;
    return () => {
      document.title = original;
    };
  }, [running, remaining]);

  // Opaque on purpose: this card is sticky over scrolling content, so a
  // translucent tint (like --chili-tint) would let exercise rows show through.
  const wrapStyle = {
    position: "sticky",
    bottom: "calc(var(--nav-height) + 8px)",
    zIndex: 5,
    marginTop: 12,
  };
  const btn = { padding: "10px 14px", fontSize: 13 };
  const pulseCss = "@keyframes fita-pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.45; } }";

  if (running) {
    return (
      <div
        className="card"
        style={{
          ...wrapStyle,
          background: "var(--timer-bg)", // opaque on purpose, see tokens.css
          border: "2px solid var(--chili)",
          boxShadow: "0 0 24px rgba(232, 73, 29, 0.45)",
        }}
        role="timer"
        aria-label="Rest timer"
      >
        <style>{pulseCss}</style>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10, flexWrap: "wrap" }}>
          <div>
            <p style={{ fontSize: 11, fontWeight: 700, letterSpacing: 1, color: "var(--text-dim)" }}>REST</p>
            <p
              className="stat"
              style={{
                fontSize: 48,
                fontWeight: 700,
                lineHeight: 1,
                color: almostDone ? "var(--turmeric)" : "var(--text)",
                animation: almostDone ? "fita-pulse 1s ease-in-out infinite" : "none",
              }}
            >
              {formatClock(remaining)}
            </p>
          </div>
          <div style={{ display: "flex", gap: 6 }}>
            <button className="btn btn-secondary" style={btn} onClick={() => adjust(-15)}>−15s</button>
            <button className="btn btn-secondary" style={btn} onClick={() => adjust(15)}>+15s</button>
            <button className="btn btn-primary" style={btn} onClick={stop}>Skip</button>
          </div>
        </div>
        <div style={{ height: 8, borderRadius: 4, background: "var(--timer-track)", marginTop: 12, overflow: "hidden" }}>
          <div style={{ width: `${progress}%`, height: "100%", background: "var(--chili)", transition: "width 0.25s linear" }} />
        </div>
      </div>
    );
  }

  if (finished) {
    const whiteBtn = { ...btn, background: "#fff", color: "var(--chili-dim)", border: "none", fontWeight: 700 };
    return (
      <div
        className="card"
        style={{
          ...wrapStyle,
          background: "var(--chili)",
          border: "2px solid var(--chili)",
          color: "#fff",
          boxShadow: "0 0 28px rgba(232, 73, 29, 0.6)",
          animation: "fita-pulse 1s ease-in-out 3",
        }}
        role="status"
      >
        <style>{pulseCss}</style>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10, flexWrap: "wrap" }}>
          <p style={{ fontSize: 18, fontWeight: 700 }}>Rest over: next set!</p>
          <div style={{ display: "flex", gap: 6 }}>
            <button style={whiteBtn} onClick={() => start(duration)}>
              Rest again ({formatClock(duration)})
            </button>
            <button style={whiteBtn} onClick={dismiss}>Done</button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div
      className="card"
      style={{ ...wrapStyle, background: "var(--bg-raised)", border: "1px solid var(--chili-dim)" }}
    >
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8, flexWrap: "wrap" }}>
        <p style={{ fontSize: 13, fontWeight: 600, color: "var(--text-dim)" }}>Rest timer</p>
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          {PRESETS.map((s) => (
            <button key={s} className="btn btn-secondary" style={btn} onClick={() => start(s)}>
              {formatClock(s)}
            </button>
          ))}
        </div>
      </div>
      <label style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 8, fontSize: 12, color: "var(--text-dim)", cursor: "pointer" }}>
        <input
          type="checkbox"
          checked={autoStart}
          onChange={(e) => setAutoStart(e.target.checked)}
          style={{ width: "auto", margin: 0 }}
        />
        Start automatically
      </label>
    </div>
  );
}