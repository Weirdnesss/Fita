import { useState } from "react";

const STORAGE_KEY = "fita_chat_detail";

// Remembers the choice across sessions on this device.
export function useChatDetail() {
  const [detail, setDetail] = useState(() => {
    try {
      return localStorage.getItem(STORAGE_KEY) === "detailed" ? "detailed" : "short";
    } catch {
      return "short";
    }
  });

  function update(next) {
    setDetail(next);
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      /* storage unavailable -- the choice just won't persist */
    }
  }

  return [detail, update];
}

export default function DetailToggle({ value, onChange }) {
  return (
    <div
      role="group"
      aria-label="Answer length"
      style={{ display: "flex", border: "1px solid var(--border)", borderRadius: 8, overflow: "hidden", flexShrink: 0 }}
    >
      {[
        ["short", "Short"],
        ["detailed", "Detailed"],
      ].map(([key, label]) => (
        <button
          key={key}
          onClick={() => onChange(key)}
          aria-pressed={value === key}
          style={{
            padding: "6px 12px",
            fontSize: 12,
            fontWeight: 600,
            border: "none",
            background: value === key ? "var(--chili)" : "transparent",
            color: value === key ? "#fff" : "var(--text-dim)",
          }}
        >
          {label}
        </button>
      ))}
    </div>
  );
}