import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import PageHeader from "../../components/PageHeader";
import { Loading, ErrorBanner, EmptyState, extractErrorMessage } from "../../components/Status";
import { listTemplates, listHistory, deleteTemplate, generateWorkout } from "../../api/workouts";

export default function WorkoutsDashboard() {
  const navigate = useNavigate();
  const [templates, setTemplates] = useState(null);
  const [history, setHistory] = useState(null);
  const [error, setError] = useState("");
  const [generating, setGenerating] = useState(false);

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

  async function handleGenerate() {
    setGenerating(true);
    setError("");
    try {
      await generateWorkout();
      // Re-fetch rather than patch local state in place: one Generate
      // call can create/replace multiple day-type routines at once
      // (the whole split), so a full refresh is simplest to keep correct.
      await load();
    } catch (err) {
      const nextEligible = err?.response?.data?.next_eligible_at;
      if (err?.response?.status === 429 && nextEligible) {
        setError(`Workouts can only be generated once a week. You can generate again on ${new Date(nextEligible).toLocaleDateString(undefined, { weekday: "long", month: "short", day: "numeric" })}.`);
      } else {
        setError(extractErrorMessage(err, "Couldn't generate a workout."));
      }
    } finally {
      setGenerating(false);
    }
  }

  async function handleDelete(id, title) {
    if (!window.confirm(`Delete "${title}"? This can't be undone.`)) return;
    try {
      await deleteTemplate(id);
      setTemplates((prev) => prev.filter((t) => t.id !== id));
    } catch (err) {
      setError(extractErrorMessage(err));
    }
  }

  return (
    <div className="page">
      <PageHeader title="Workouts" subtitle="Organize your routines" />
      <ErrorBanner message={error} />

      <div className="card" style={{ marginBottom: 20, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <p style={{ fontWeight: 600 }}>Generate a workout</p>
          <p style={{ fontSize: 12, color: "var(--text-faint)" }}>
            Built from your goal, frequency, and location · once a week
          </p>
        </div>
        <button className="btn btn-primary" style={{ padding: "8px 14px", fontSize: 13 }} onClick={handleGenerate} disabled={generating}>
          {generating ? "Generating..." : "Generate"}
        </button>
      </div>

      <div>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
          <h3>My Routines</h3>
          <button className="btn btn-primary" style={{ padding: "8px 14px", fontSize: 13 }} onClick={() => navigate("/workouts/new")}>
            + Create
          </button>
        </div>
        {templates === null && <Loading />}
        {templates?.length === 0 && <EmptyState title="No templates added yet" />}
        {templates?.map((r) => (
          <div key={r.id} className="card" style={{ marginBottom: 10 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
              <div>
                <p style={{ fontWeight: 600 }}>{r.title}</p>
                <p style={{ fontSize: 12, color: "var(--text-faint)" }}>{r.exercises.length} exercises</p>
              </div>
              {r.is_generated && <span className="pill pill-bamboo">Generated</span>}
            </div>
            <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
              {!r.is_generated && (
                <button
                  className="btn btn-secondary"
                  style={{ padding: "6px 12px", fontSize: 12 }}
                  onClick={() => navigate(`/workouts/templates/${r.id}`)}
                >
                  Edit
                </button>
              )}
              {r.is_generated && (
                <button
                  className="btn btn-secondary"
                  style={{ padding: "6px 12px", fontSize: 12 }}
                  onClick={() => navigate(`/workouts/templates/${r.id}`)}
                >
                  View / Swap
                </button>
              )}
              <button
                className="btn btn-primary"
                style={{ padding: "6px 12px", fontSize: 12 }}
                onClick={() => navigate(`/workouts/templates/${r.id}/start`)}
              >
                Start
              </button>
              <button
                className="btn-ghost"
                style={{ background: "none", border: "1px solid var(--border)", color: "var(--chili)", fontSize: 12, padding: "6px 12px", borderRadius: "var(--radius)" }}
                onClick={() => handleDelete(r.id, r.title)}
              >
                Delete
              </button>
            </div>
          </div>
        ))}
      </div>

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
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", marginTop: 10 }}>
              <div style={{ display: "flex", gap: 16 }}>
                <MiniStat label="Exercises" value={h.total_exercises} />
                <MiniStat label="Sets" value={h.total_sets} />
              </div>
              <button
                className="btn btn-secondary"
                style={{ padding: "6px 12px", fontSize: 12 }}
                onClick={() => navigate(`/workouts/history/${h.id}`)}
              >
                View
              </button>
            </div>
          </div>
        ))}
      </div>
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