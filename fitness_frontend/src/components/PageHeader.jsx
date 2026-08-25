import { useNavigate } from "react-router-dom";

export default function PageHeader({ title, subtitle, back, action }) {
  const navigate = useNavigate();
  return (
    <header style={styles.header}>
      <div style={styles.top}>
        {back && (
          <button onClick={() => navigate(-1)} style={styles.backBtn} aria-label="Go back">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <path d="M15 18l-6-6 6-6" />
            </svg>
          </button>
        )}
        <h1 style={{ flex: 1 }}>{title}</h1>
        {action}
      </div>
      {subtitle && <p style={styles.subtitle}>{subtitle}</p>}
    </header>
  );
}

const styles = {
  header: { display: "flex", flexDirection: "column", gap: 4 },
  top: { display: "flex", alignItems: "center", gap: 10 },
  backBtn: {
    background: "none",
    border: "none",
    color: "var(--text)",
    padding: 4,
    display: "flex",
  },
  subtitle: { color: "var(--text-dim)", fontSize: 14 },
};
