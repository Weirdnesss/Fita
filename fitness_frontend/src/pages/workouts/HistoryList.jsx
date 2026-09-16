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

export default function HistoryList() {
  const navigate = useNavigate();

    const [history, setHistory] = useState(null);
    const [error, setError] = useState("");
    const [page, setPage] = useState(1);

    const ITEMS_PER_PAGE = 3;

  useEffect(() => {
    load();
  }, []);

  const totalPages = history
    ? Math.ceil(history.length / ITEMS_PER_PAGE)
    : 0;

  const startIndex = (page - 1) * ITEMS_PER_PAGE;

  const visibleHistory = history
    ? history.slice(startIndex, startIndex + ITEMS_PER_PAGE)
    : [];

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
          {totalPages > 1 && (
            <div className="pagination">
                <button
                className="btn btn-secondary"
                onClick={() => setPage((p) => p - 1)}
                disabled={page === 1}
                >
                Previous
                </button>

                <span className="pagination-info">
                Page {page} of {totalPages}
                </span>

                <button
                className="btn btn-secondary"
                onClick={() => setPage((p) => p + 1)}
                disabled={page === totalPages}
                >
                Next
                </button>
            </div>
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