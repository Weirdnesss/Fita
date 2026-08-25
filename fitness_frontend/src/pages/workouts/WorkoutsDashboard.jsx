import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import PageHeader from "../../components/PageHeader";
import { Loading, ErrorBanner, EmptyState, extractErrorMessage } from "../../components/Status";
import { listTemplates, listHistory, deleteTemplate } from "../../api/workouts";

export default function WorkoutsDashboard() {
  const navigate = useNavigate();
  const [templates, setTemplates] = useState(null);
  const [history, setHistory] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    load();
  }, []);

  async function load() {
    try {
      const [t, h] = await Promise.all([listTemplates(), listHistory()]);
      setTemplates(t);
      setHistory(h);
    } catch (err) {
      setError(extractErrorMessage(err));
    }
  }

  async function handleDelete(id) {
    try {
      await deleteTemplate(id);
      setTemplates((prev) => prev.filter((t) => t.id !== id));
    } catch (err) {
      setError(extractErrorMessage(err));
    }
  }

  const mainRoutines = templates?.filter((t) => t.kind === "main") ?? [];
  const altRoutines = templates?.filter((t) => t.kind === "alternative") ?? [];

  return (
    <div className="page">
      <PageHeader title="Workouts" subtitle="Organize your routines" />
      <ErrorBanner message={error} />

      <RoutineSection
        title="My Routines"
        routines={mainRoutines}
        loading={templates === null}
        onCreate={() => navigate("/workouts/new?kind=main")}
        onOpen={(id) => navigate(`/workouts/templates/${id}`)}
        onDelete={handleDelete}
      />

      <RoutineSection
        title="Alternative Routines"
        routines={altRoutines}
        loading={templates === null}
        onCreate={() => navigate("/workouts/new?kind=alternative")}
        onOpen={(id) => navigate(`/workouts/templates/${id}`)}
        onDelete={handleDelete}
      />

      <div>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
          <h3>History {history ? `(${history.length})` : ""}</h3>
        </div>
        {history === null && <Loading />}
        {history?.length === 0 && <EmptyState title="No workouts logged yet" />}
        {history?.slice(0, 10).map((h) => (
          <div key={h.id} className="card" style={{ marginBottom: 10 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
              <div>
                <p style={{ fontWeight: 600 }}>{h.template_title}</p>
                <p style={{ fontSize: 12, color: "var(--text-faint)" }}>
                  {new Date(h.completed_at).toLocaleDateString()}
                </p>
              </div>
              <span className="pill pill-bamboo">{h.duration_minutes} min</span>
            </div>
            <div style={{ display: "flex", gap: 16, marginTop: 10 }}>
              <MiniStat label="Exercises" value={h.total_exercises} />
              <MiniStat label="Sets" value={h.total_sets} />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function RoutineSection({ title, routines, loading, onCreate, onOpen, onDelete }) {
  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
        <h3>{title}</h3>
        <button className="btn btn-primary" style={{ padding: "8px 14px", fontSize: 13 }} onClick={onCreate}>
          + Create
        </button>
      </div>
      {loading && <Loading />}
      {!loading && routines.length === 0 && <EmptyState title="No templates added yet" />}
      {routines.map((r) => (
        <div key={r.id} className="card card-tab" style={{ marginBottom: 10 }} onClick={() => onOpen(r.id)}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <div>
              <p style={{ fontWeight: 600 }}>{r.title}</p>
              <p style={{ fontSize: 12, color: "var(--text-faint)" }}>{r.exercises.length} exercises</p>
            </div>
            <button
              className="btn-ghost"
              style={{ background: "none", border: "none", color: "var(--chili)", fontSize: 12 }}
              onClick={(e) => {
                e.stopPropagation();
                onDelete(r.id);
              }}
            >
              Delete
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}

function MiniStat({ label, value }) {
  return (
    <div>
      <div className="stat" style={{ fontSize: 15 }}>{value}</div>
      <div className="eyebrow">{label}</div>
    </div>
  );
}
