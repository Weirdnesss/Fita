import { useEffect, useState } from "react";
import PageHeader from "../../components/PageHeader";
import { Loading, ErrorBanner, EmptyState, extractErrorMessage } from "../../components/Status";
import { listResources } from "../../api/resources";

// Mirrors resources.models.ResourceCategory on the backend.
const CATEGORIES = [
  ["workout", "Workout"],
  ["nutrition", "Nutrition"],
  ["general", "General"],
];

export default function ResourcesList() {
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState(null);
  const [resources, setResources] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    const t = setTimeout(async () => {
      try {
        const r = await listResources({ category, q: query });
        setResources(r);
      } catch (err) {
        setError(extractErrorMessage(err));
      }
    }, 300);
    return () => clearTimeout(t);
  }, [query, category]);

  return (
    <div className="page">
      <PageHeader title="Resources" subtitle="Workout & Nutrition Articles" />
      <input placeholder="Search articles" value={query} onChange={(e) => setQuery(e.target.value)} />

      <div style={{ display: "flex", gap: 6, overflowX: "auto", paddingBottom: 4 }}>
        <CategoryChip active={category === null} label="All" onClick={() => setCategory(null)} />
        {CATEGORIES.map(([value, label]) => (
          <CategoryChip key={value} active={category === value} label={label} onClick={() => setCategory(category === value ? null : value)} />
        ))}
      </div>

      <ErrorBanner message={error} />
      {resources === null && <Loading />}
      {resources?.length === 0 && (
        <EmptyState title="No resources yet" eyebrow="Nothing here yet -- check back later" />
      )}
      {resources?.map((r) => (
        <a
          key={r.id}
          href={r.url}
          target="_blank"
          rel="noreferrer noopener"
          className="card card-tab"
          style={{ marginBottom: 10, display: "block", textDecoration: "none", color: "inherit" }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 8, marginBottom: 6 }}>
            <p style={{ fontWeight: 600 }}>{r.title}</p>
            <CategoryPill category={r.category} />
          </div>
          {r.summary && (
            <p style={{ fontSize: 13, color: "var(--text-dim)", marginBottom: 6 }}>{r.summary}</p>
          )}
          {r.source && <p style={{ fontSize: 12, color: "var(--text-faint)" }}>{r.source}</p>}
        </a>
      ))}
    </div>
  );
}

function CategoryChip({ active, label, onClick }) {
  return (
    <button
      onClick={onClick}
      className={active ? "btn btn-primary" : "btn btn-secondary"}
      style={{ padding: "6px 12px", fontSize: 12, whiteSpace: "nowrap", flexShrink: 0, height: "auto" }}
    >
      {label}
    </button>
  );
}

function CategoryPill({ category }) {
  const map = {
    workout: "pill-chili",
    nutrition: "pill-bamboo",
    general: "pill-turmeric",
  };
  const label = CATEGORIES.find(([v]) => v === category)?.[1] || category;
  return <span className={`pill ${map[category] || "pill-turmeric"}`} style={{ flexShrink: 0 }}>{label}</span>;
}