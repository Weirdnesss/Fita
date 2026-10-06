import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../../context/AuthContext";
import { deleteWeightLog } from "../../api/accounts";
import { extractErrorMessage } from "../Status";
import ConfirmDialog from "../ConfirmDialog";
import { formatWeight } from "../../lib/profile";
import { useToast } from "../../context/ToastContext";

const PAGE_SIZE = 10;

function formatLogDate(dateStr) {
  return new Date(dateStr + "T00:00:00").toLocaleDateString();
}

// `limit`: compact rows capped at N with a link to the full history page
// (used on the embedded Profile card). Without it, entries render as
// cards with Load More pagination (the dedicated /profile/weight page).
export default function WeightHistoryList({ logs, unitSystem, limit, onDeleted, heading }) {
  const { refreshUser } = useAuth();
  const showToast = useToast();
  const navigate = useNavigate();
  const [deletingId, setDeletingId] = useState(null);
  const [pendingDelete, setPendingDelete] = useState(null); // { id, weightKg } | null
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);

  async function confirmDelete() {
    const { id, weightKg } = pendingDelete;
    setPendingDelete(null);
    setDeletingId(id);
    try {
      await deleteWeightLog(id);
      await refreshUser();
      showToast(`Deleted ${formatWeight(weightKg, unitSystem)} entry`, "success");
      onDeleted?.();
    } catch (err) {
      showToast(extractErrorMessage(err, "Couldn't delete that entry."), "error");
    } finally {
      setDeletingId(null);
    }
  }

  const asCards = false;
  const visible = limit ? logs?.slice(0, limit) : logs?.slice(0, visibleCount);
  const hasMoreLink = limit && logs && logs.length > limit;
  const hasMoreToLoad = !limit && logs && logs.length > visibleCount;

  function renderCard(entry) {
    return (
      <div
        key={entry.id}
        className="card card-accent"
        style={{
          marginBottom: 10,
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          "--accent-color": "var(--bamboo)",
        }}
      >
        <div>
          <p className="stat" style={{ fontSize: 16 }}>{formatWeight(entry.weight_kg, unitSystem)}</p>
          <p style={{ fontSize: 12, color: "var(--text-faint)" }}>{formatLogDate(entry.logged_at)}</p>
        </div>
        <button
          className="btn-ghost"
          style={{ fontSize: 12 }}
          onClick={() => setPendingDelete({ id: entry.id, weightKg: entry.weight_kg })}
          disabled={deletingId === entry.id}
        >
          {deletingId === entry.id ? "Deleting..." : "Delete"}
        </button>
      </div>
    );
  }

  function renderRow(entry) {
    return (
      <div
        key={entry.id}
        style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "8px 0", borderBottom: "1px solid var(--border)" }}
      >
        <div>
          <p style={{ fontWeight: 600, fontSize: 14 }}>{formatWeight(entry.weight_kg, unitSystem)}</p>
          <p style={{ fontSize: 12, color: "var(--text-faint)" }}>{formatLogDate(entry.logged_at)}</p>
        </div>
        <button
          className="btn-ghost"
          style={{ fontSize: 12, padding: 6 }}
          onClick={() => setPendingDelete({ id: entry.id, weightKg: entry.weight_kg })}
          disabled={deletingId === entry.id}
        >
          {deletingId === entry.id ? "Deleting..." : "Delete"}
        </button>
      </div>
    );
  }

  return (
    <div>
      {heading && <h3 style={{ marginBottom: 10 }}>{heading}</h3>}
      {logs !== null && logs.length === 0 && (
        <p style={{ fontSize: 13, color: "var(--text-faint)" }}>No entries yet -- log your first weight above.</p>
      )}

      <div className={asCards ? "weight-history-grid" : undefined}>
        {visible?.map((entry) => (asCards ? renderCard(entry) : renderRow(entry)))}
      </div>

      {hasMoreLink && (
        <button
          className="btn-ghost"
          style={{ padding: "10px 0 0", fontSize: 13, fontWeight: 600 }}
          onClick={() => navigate("/profile/weight")}
        >
          View full history ({logs.length}) &rarr;
        </button>
      )}
      {hasMoreToLoad && (
        <button
          className="btn btn-secondary"
          style={{ width: "100%", marginTop: 10 }}
          onClick={() => setVisibleCount((c) => c + PAGE_SIZE)}
        >
          Load More ({logs.length - visibleCount} left)
        </button>
      )}

      <ConfirmDialog
        open={pendingDelete !== null}
        title="Delete entry"
        message={pendingDelete ? `Delete the ${formatWeight(pendingDelete.weightKg, unitSystem)} entry? This can't be undone.` : ""}
        confirmLabel="Delete"
        onConfirm={confirmDelete}
        onCancel={() => setPendingDelete(null)}
      />
    </div>
  );
}