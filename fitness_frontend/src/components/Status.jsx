import { useState } from "react";

export function Loading({ label = "Loading" }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "24px 0", color: "var(--text-dim)" }}>
      <span className="spinner" />
      <span>{label}...</span>
    </div>
  );
}

export function ErrorBanner({ message }) {
  if (!message) return null;
  return (
    <div
      style={{
        background: "var(--chili-tint)",
        border: "1px solid var(--chili-dim)",
        borderRadius: "var(--radius-sm)",
        padding: "10px 12px",
        color: "var(--chili)",
        fontSize: 13,
      }}
    >
      {message}
    </div>
  );
}

export function OfflineBanner() {
  return (
    <div
      style={{
        background: "var(--turmeric-tint)",
        border: "1px solid var(--turmeric)",
        borderRadius: "var(--radius-sm)",
        padding: "10px 12px",
        color: "var(--turmeric)",
        fontSize: 13,
        display: "flex",
        alignItems: "center",
        gap: 8,
      }}
    >
      <span>You're offline. You can still view previously loaded data -- logging or saving changes needs a connection.</span>
    </div>
  );
}

const INSTALL_DISMISSED_KEY = "fitness_assistant_install_dismissed";

export function InstallBanner({ canInstall, isIosManualInstall, onInstall }) {
  const [dismissed, setDismissed] = useState(
    () => localStorage.getItem(INSTALL_DISMISSED_KEY) === "1"
  );

  if (dismissed || (!canInstall && !isIosManualInstall)) return null;

  function dismiss() {
    localStorage.setItem(INSTALL_DISMISSED_KEY, "1");
    setDismissed(true);
  }

  return (
    <div
      style={{
        background: "var(--chili-tint)",
        border: "1px solid var(--chili-dim)",
        borderRadius: "var(--radius-sm)",
        padding: "10px 12px",
        color: "var(--chili)",
        fontSize: 13,
        display: "flex",
        alignItems: "center",
        gap: 8,
      }}
    >
      <span style={{ flex: 1 }}>
        {canInstall
          ? "Install Fita on this device for quicker access and offline viewing."
          : "Add Fita to your Home Screen: tap Share, then \"Add to Home Screen\"."}
      </span>
      {canInstall && (
        <button
          onClick={onInstall}
          style={{
            background: "var(--chili)",
            color: "#fff",
            border: "none",
            borderRadius: "var(--radius-sm)",
            padding: "6px 12px",
            fontSize: 13,
            fontWeight: 600,
            cursor: "pointer",
            flexShrink: 0,
          }}
        >
          Install
        </button>
      )}
      <button
        onClick={dismiss}
        aria-label="Dismiss"
        style={{
          background: "transparent",
          border: "none",
          color: "var(--chili)",
          cursor: "pointer",
          fontSize: 16,
          lineHeight: 1,
          padding: 4,
          flexShrink: 0,
        }}
      >
        &times;
      </button>
    </div>
  );
}

export function EmptyState({ eyebrow, title, action }) {
  return (
    <div className="empty-state">
      {eyebrow && <span className="eyebrow">{eyebrow}</span>}
      <p>{title}</p>
      {action && <div style={{ marginTop: 16 }}>{action}</div>}
    </div>
  );
}

export function extractErrorMessage(err, fallback = "Something went wrong. Please try again.") {
  const data = err?.response?.data;
  if (!data) return fallback;
  if (typeof data === "string") return data;
  if (data.error) return data.error;
  if (data.detail) return data.detail;
  // DRF validation errors: {field: ["msg"]}
  const firstKey = Object.keys(data)[0];
  if (firstKey) {
    const val = data[firstKey];
    return Array.isArray(val) ? val[0] : String(val);
  }
  return fallback;
}
