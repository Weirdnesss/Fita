import { useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";

export default function PageHeader({ title, subtitle, back, backTo, onBack, action }) {
  const navigate = useNavigate();
  const handleBack = onBack || (() => (backTo ? navigate(backTo) : navigate(-1)));
  const headerRef = useRef(null);

  // Publishes the header's height as --page-header-h so controls that should stay
  // on screen (search bars, action buttons) can stick just below it with
  // `position: sticky; top: var(--page-header-h, 0px)`.
  useEffect(() => {
    const el = headerRef.current;
    if (!el) return;
    const root = document.documentElement;
    const previous = root.style.getPropertyValue("--page-header-h"); // an outer header, if nested
    const publish = () => root.style.setProperty("--page-header-h", `${el.offsetHeight}px`);
    publish();
    const observer = typeof ResizeObserver !== "undefined" ? new ResizeObserver(publish) : null;
    observer?.observe(el);
    return () => {
      observer?.disconnect();
      if (previous) root.style.setProperty("--page-header-h", previous);
      else root.style.removeProperty("--page-header-h");
    };
  }, []);

  return (
    <header ref={headerRef} style={styles.header}>
      <div style={styles.top}>
        {back && (
          <button
            onClick={handleBack}
            style={styles.backBtn}
            aria-label="Go back"
          >
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
  header: {
    display: "flex",
    flexDirection: "column",
    gap: 4,
    position: "sticky",
    top: 0,
    zIndex: 10,
    background: "var(--bg)",
    paddingBottom: 10,
  },
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