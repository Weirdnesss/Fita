export default function UnitToggle({ options, value, onChange }) {
  return (
    <div style={{ display: "flex", gap: 4 }}>
      {options.map((opt) => (
        <button
          key={opt.value}
          type="button"
          onClick={() => onChange(opt.value)}
          style={{
            fontSize: 11,
            fontWeight: 600,
            padding: "3px 8px",
            borderRadius: "var(--radius-sm)",
            border: `1px solid ${value === opt.value ? "var(--chili)" : "var(--border)"}`,
            background: value === opt.value ? "var(--chili-tint)" : "transparent",
            color: value === opt.value ? "var(--chili)" : "var(--text-dim)",
            cursor: "pointer",
          }}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}
