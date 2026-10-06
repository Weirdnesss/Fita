export default function SegmentedControl({ options, value, onChange }) {
  return (
    <div style={{ display: "flex", border: "1px solid var(--border)", borderRadius: 8, overflow: "hidden" }}>
      {options.map(([v, label]) => (
        <button
          key={v}
          onClick={() => onChange(v)}
          aria-pressed={value === v}
          style={{
            padding: "5px 10px",
            fontSize: 12,
            fontWeight: 600,
            border: "none",
            background: value === v ? "var(--bg-raised)" : "transparent",
            color: value === v ? "var(--text)" : "var(--text-faint)",
          }}
        >
          {label}
        </button>
      ))}
    </div>
  );
}