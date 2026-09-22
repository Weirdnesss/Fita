import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import PageHeader from "../../components/PageHeader";
import { Loading, ErrorBanner, EmptyState, extractErrorMessage } from "../../components/Status";
import { listTemplates, listHistory, deleteTemplate, generateWorkout } from "../../api/workouts";
import ConfirmDialog from "../../components/ConfirmDialog";
import { useToast } from "../../context/ToastContext";
import WorkoutTrendsPanel from "./WorkoutTrendsPanel";

// Generated routines cap at 6 forever (one per day-type -- see
// workouts/models.py's one_generated_template_per_day_type_per_user
// constraint), so 6 comfortably shows a full generated split without
// "Load More". Self-made routines have no such cap, so this is what
// keeps that list from growing unbounded on screen.
const TEMPLATES_PAGE_SIZE = 6;

// History has no such cap -- every completed workout lands here --
// so it gets the same "Load More" treatment as the old standalone
// /workouts/history page did.
const HISTORY_PAGE_SIZE = 10;

export default function WorkoutsDashboard() {
  const navigate = useNavigate();
  const showToast = useToast();
  const [templates, setTemplates] = useState(null);
  const [history, setHistory] = useState(null);
  const [error, setError] = useState("");
  const [generating, setGenerating] = useState(false);
  const [pendingDelete, setPendingDelete] = useState(null); // { id, title } | null
  const [filter, setFilter] = useState("all"); // "all" | "own" | "generated"
  const [medicalNote, setMedicalNote] = useState(null);
  const [visibleCount, setVisibleCount] = useState(TEMPLATES_PAGE_SIZE);
  const [activeTab, setActiveTab] = useState("routines"); // "routines" | "history" | "trends"
  const [historyVisibleCount, setHistoryVisibleCount] = useState(HISTORY_PAGE_SIZE);

  function handleFilterChange(next) {
    setFilter(next);
    setVisibleCount(TEMPLATES_PAGE_SIZE); // switching filters starts back at the top of that list
  }

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
      const result = await generateWorkout();
      // Re-fetch rather than patch local state in place: one Generate
      // call can create/replace multiple day-type routines at once
      // (the whole split), so a full refresh is simplest to keep correct.
      await load();
      // A toast alone isn't right for this -- it auto-dismisses in a
      // couple seconds, and a medical/injury disclaimer needs to
      // actually be read, not just glanced at. Shown as a persistent
      // banner instead (below), which the user has to dismiss themselves.
      setMedicalNote(result.medical_note || null);
      showToast("Workout routines generated", "success");
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

  async function confirmDeleteTemplate() {
    const { id, title } = pendingDelete;
    setPendingDelete(null);
    try {
      await deleteTemplate(id);
      setTemplates((prev) => prev.filter((t) => t.id !== id));
      showToast(`Deleted "${title}"`, "success");
    } catch (err) {
      showToast(extractErrorMessage(err), "error");
    }
  }

  const ownCount = templates?.filter((r) => !r.is_generated).length ?? 0;
  const generatedCount = templates?.filter((r) => r.is_generated).length ?? 0;
  const visibleTemplates = templates?.filter((r) => {
    if (filter === "own") return !r.is_generated;
    if (filter === "generated") return r.is_generated;
    return true;
  });

  return (
    <div className="page">
      <PageHeader title="Workouts" subtitle="Organize your routines" />
      <ErrorBanner message={error} />

      {medicalNote && (
        <div className="card" style={{ borderColor: "var(--turmeric)", display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12 }}>
          <p style={{ fontSize: 13 }}>{medicalNote}</p>
          <button
            onClick={() => setMedicalNote(null)}
            style={{ background: "none", border: "none", color: "var(--text-faint)", fontSize: 12, flexShrink: 0 }}
          >
            Dismiss
          </button>
        </div>
      )}

      <div className="card workout-actions-row" style={{ marginBottom: 20 }}>
        <div>
          <p style={{ fontWeight: 600 }}>New Routine</p>
          <p style={{ fontSize: 12, color: "var(--text-faint)" }}>
            Generated plans use your goal, frequency, and location · once a week
          </p>
        </div>
        <div style={{ display: "flex", gap: 8, flexShrink: 0 }}>
          <button className="btn btn-secondary" style={{ padding: "8px 14px", fontSize: 13 }} onClick={() => navigate("/workouts/new")}>
            Build My Own
          </button>
          <button className="btn btn-primary" style={{ padding: "8px 14px", fontSize: 13 }} onClick={handleGenerate} disabled={generating}>
            {generating ? "Generating..." : "Generate for Me"}
          </button>
        </div>
      </div>

      <div className="tab-bar">
        <button
          className={`tab-btn${activeTab === "routines" ? " active" : ""}`}
          onClick={() => setActiveTab("routines")}
        >
          Routines{templates ? ` (${templates.length})` : ""}
        </button>
        <button
          className={`tab-btn${activeTab === "history" ? " active" : ""}`}
          onClick={() => setActiveTab("history")}
        >
          History{history ? ` (${history.length})` : ""}
        </button>
        <button
          className={`tab-btn${activeTab === "trends" ? " active" : ""}`}
          onClick={() => setActiveTab("trends")}
        >
          Trends
        </button>
      </div>

      {activeTab === "routines" && (
        <div>
          {ownCount > 0 && generatedCount > 0 && (
            <div style={{ display: "flex", gap: 8, marginBottom: 12, flexWrap: "wrap" }}>
              <FilterChip active={filter === "all"} label={`All (${templates.length})`} onClick={() => handleFilterChange("all")} />
              <FilterChip active={filter === "own"} label={`Own (${ownCount})`} onClick={() => handleFilterChange("own")} />
              <FilterChip active={filter === "generated"} label={`Generated (${generatedCount})`} onClick={() => handleFilterChange("generated")} />
            </div>
          )}

          {templates === null && <Loading />}
          {templates?.length === 0 && <EmptyState title="No templates added yet" />}
          {templates?.length > 0 && visibleTemplates.length === 0 && (
            <EmptyState title={filter === "own" ? "No routines you've created yet" : "No generated routines yet"} />
          )}

          {visibleTemplates?.length > 0 && (
            <div className="workout-template-grid">
              {visibleTemplates.slice(0, visibleCount).map((r) => (
                <div
                  key={r.id}
                  className="card card-accent"
                  style={{
                    marginBottom: 10,
                    "--accent-color": `var(--${r.is_generated ? "bamboo" : "turmeric"})`,
                  }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 8 }}>
                    <p style={{ fontWeight: 600 }}>{r.title}</p>
                    {r.is_generated && <span className="pill pill-bamboo">Generated</span>}
                  </div>
                  <p style={{ fontSize: 12, color: "var(--text-faint)", marginBottom: 12 }}>{r.exercises.length} exercises</p>
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10 }}>
                    <button
                      className="btn btn-primary"
                      style={{ padding: "8px 14px", fontSize: 13 }}
                      onClick={() => navigate(`/workouts/templates/${r.id}/start`)}
                    >
                      Start Workout
                    </button>
                    <div style={{ display: "flex", gap: 16 }}>
                      <button className="btn-ghost" onClick={() => navigate(`/workouts/templates/${r.id}`)}>
                        {r.is_generated ? "View / Swap" : "Edit"}
                      </button>
                      <button className="btn-ghost" onClick={() => setPendingDelete({ id: r.id, title: r.title })}>
                        Delete
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}

          {visibleTemplates?.length > visibleCount && (
            <button
              className="btn btn-secondary"
              style={{ width: "100%", marginTop: 4 }}
              onClick={() => setVisibleCount((c) => c + TEMPLATES_PAGE_SIZE)}
            >
              Show More ({visibleTemplates.length - visibleCount} left)
            </button>
          )}
        </div>
      )}

      {activeTab === "history" && (
        <div>
          {history === null && <Loading />}
          {history?.length === 0 && <EmptyState title="No workouts logged yet" />}

          {history?.length > 0 && (
            <div>
              <div className="workout-history-grid">
                {history.slice(0, historyVisibleCount).map((h) => (
                  <div key={h.id} className="card" style={{ marginBottom: 10 }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12 }}>
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

              {history.length > historyVisibleCount && (
                <button
                  className="btn btn-secondary"
                  style={{ width: "100%", marginTop: 4 }}
                  onClick={() => setHistoryVisibleCount((c) => c + HISTORY_PAGE_SIZE)}
                >
                  Load More ({history.length - historyVisibleCount} left)
                </button>
              )}
            </div>
          )}
        </div>
      )}

      {activeTab === "trends" && <WorkoutTrendsPanel />}

      <ConfirmDialog
        open={pendingDelete !== null}
        title="Delete routine"
        message={pendingDelete ? `Delete "${pendingDelete.title}"? This can't be undone.` : ""}
        confirmLabel="Delete"
        onConfirm={confirmDeleteTemplate}
        onCancel={() => setPendingDelete(null)}
      />
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

function FilterChip({ active, label, onClick }) {
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