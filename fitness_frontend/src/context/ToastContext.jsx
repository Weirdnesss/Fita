import { createContext, useCallback, useContext, useRef, useState } from "react";

const ToastContext = createContext(null);

const COLORS = {
  success: { bg: "var(--bamboo-tint)", border: "var(--bamboo)", text: "var(--bamboo)" },
  error: { bg: "var(--chili-tint)", border: "var(--chili-dim)", text: "var(--chili)" },
};

/**
 * Mounted once near the app root (see App.jsx) so a toast fired from any
 * page survives a navigation that happens right after it -- e.g. adding a
 * food logs a toast, then immediately navigates back to the dashboard;
 * the toast needs to still be alive on the page it lands on.
 */
export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);
  const idRef = useRef(0);

  const showToast = useCallback((message, type = "success") => {
    const id = ++idRef.current;
    setToasts((t) => [...t, { id, message, type }]);
    setTimeout(() => {
      setToasts((t) => t.filter((x) => x.id !== id));
    }, 3000);
  }, []);

  return (
    <ToastContext.Provider value={showToast}>
      {children}
      <div
        style={{
          position: "fixed",
          bottom: "calc(var(--nav-height) + 16px)",
          left: 16,
          right: 16,
          display: "flex",
          flexDirection: "column",
          gap: 8,
          alignItems: "center",
          zIndex: 1000,
          pointerEvents: "none",
        }}
      >
        {toasts.map((t) => {
          const c = COLORS[t.type] || COLORS.success;
          return (
            <div
              key={t.id}
              style={{
                background: c.bg,
                border: `1px solid ${c.border}`,
                color: c.text,
                borderRadius: "var(--radius-sm)",
                padding: "10px 16px",
                fontSize: 13,
                fontWeight: 600,
                maxWidth: 400,
                textAlign: "center",
                boxShadow: "0 4px 16px rgba(0,0,0,0.3)",
              }}
            >
              {t.message}
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
}

/** Returns showToast(message, type) -- type is "success" (default) or "error". */
export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used within a ToastProvider");
  return ctx;
}
