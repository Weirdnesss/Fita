import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import PageHeader from "../../components/PageHeader";
import {
  Loading,
  ErrorBanner,
  EmptyState,
  extractErrorMessage,
} from "../../components/Status";

import { listHistory } from "../../api/workouts";

const HISTORY_PAGE_SIZE = 10;

export default function HistoryList() {
  const navigate = useNavigate();

  const [history, setHistory] = useState(null);
  const [error, setError] = useState("");
  const [visibleCount, setVisibleCount] = useState(HISTORY_PAGE_SIZE);

  useEffect(() => {
    load();
  }, []);

  const visibleHistory = history ? history.slice(0, visibleCount) : [];

  async function load() {
    try {
      setError("");
      const data = await listHistory();
      setHistory(data);
    } catch (err) {
      setError(extractErrorMessage(err));
    }
  }

  return (
    <div className="page">
      <PageHeader
        title="Workout History"
        subtitle="Your completed workouts"
        back
        backTo="/workouts"
      />

      <ErrorBanner message={error} />

      {history === null && <Loading />}

      {history?.length === 0 && (
        <EmptyState title="No workouts logged yet" />
      )}

      {history?.length > 0 && (
        <div>
          <div className="workout-history-grid">
          {visibleHistory.map((h) => (
            <div
              key={h.id}
              className="card"
              style={{ marginBottom: 10 }}
            >
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "flex-start",
                  gap: 12,
                }}
              >
                <div>
                  <p style={{ fontWeight: 600 }}>
                    {h.template_title}
                  </p>

                  <p
                    style={{
                      fontSize: 12,
                      color: "var(--text-faint)",
                    }}
                  >
                    {new Date(h.completed_at).toLocaleDateString()}
                  </p>
                </div>

                <span className="pill pill-bamboo">
                  {h.duration_minutes} min
                </span>
              </div>

              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "flex-end",
                  marginTop: 10,
                }}
              >
                <div style={{ display: "flex", gap: 16 }}>
                  <MiniStat
                    label="Exercises"
                    value={h.total_exercises}
                  />

                  <MiniStat
                    label="Sets"
                    value={h.total_sets}
                  />
                </div>

                <button
                  className="btn btn-secondary"
                  style={{
                    padding: "6px 12px",
                    fontSize: 12,
                  }}
                  onClick={() =>
                    navigate(`/workouts/history/${h.id}`)
                  }
                >
                  View
                </button>
              </div>
            </div>
          ))}
          </div>
          {history.length > visibleCount && (
            <button
              className="btn btn-secondary"
              style={{ width: "100%", marginTop: 4 }}
              onClick={() => setVisibleCount((c) => c + HISTORY_PAGE_SIZE)}
            >
              Load More ({history.length - visibleCount} left)
            </button>
          )}
        </div>
      )}
    </div>
  );
}

function MiniStat({ label, value }) {
  return (
    <div>
      <div className="stat" style={{ fontSize: 15 }}>
        {value}
      </div>

      <div className="eyebrow">{label}</div>
    </div>
  );
}