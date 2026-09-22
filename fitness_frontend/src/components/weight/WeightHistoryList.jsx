import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../../context/AuthContext";
import { deleteWeightLog } from "../../api/accounts";
import { extractErrorMessage } from "../Status";
import ConfirmDialog from "../ConfirmDialog";
import { formatWeight } from "../../lib/profile";
import { useToast } from "../../context/ToastContext";

const PAGE_SIZE = 10;

// `limit`: cap how many entries show, with a link to the full history
// page for the rest (used on the embedded Profile card). Omit it for
// the dedicated /profile/weight page, which instead paginates via
// Load More rather than showing everything at once or linking anywhere
// (there's nowhere further to link to -- this already is the full-history page).
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
      showToast(`Removed ${formatWeight(weightKg, unitSystem)} entry`, "success");
      onDeleted?.();
    } catch (err) {
      showToast(extractErrorMessage(err, "Couldn't delete that entry."), "error");
    } finally {
      setDeletingId(null);
    }
  }

  const visible = limit ? logs?.slice(0, limit) : logs?.slice(0, visibleCount);
  const hasMoreLink = limit && logs && logs.length > limit;
  const hasMoreToLoad = !limit && logs && logs.length > visibleCount;

  return (
    <div>
      {heading && <h3 style={{ marginBottom: 10 }}>{heading}</h3>}
      {logs !== null && logs.length === 0 && (
        <p style={{ fontSize: 13, color: "var(--text-faint)" }}>No entries yet -- log your first weight above.</p>
      )}
      {visible?.map((entry) => (
        <div key={entry.id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "8px 0", borderBottom: "1px solid var(--border)" }}>
          <div>
            <p style={{ fontWeight: 600, fontSize: 14 }}>{formatWeight(entry.weight_kg, unitSystem)}</p>
            <p style={{ fontSize: 12, color: "var(--text-faint)" }}>{entry.logged_at}</p>
          </div>
          <button
            className="btn-ghost"
            style={{ background: "none", border: "none", color: "var(--chili)", fontSize: 12, padding: 6 }}
            onClick={() => setPendingDelete({ id: entry.id, weightKg: entry.weight_kg })}
            disabled={deletingId === entry.id}
          >
            {deletingId === entry.id ? "Removing..." : "Remove"}
          </button>
        </div>
      ))}
      {hasMoreLink && (
        <button
          className="btn-ghost"
          style={{ background: "none", border: "none", padding: "10px 0 0", fontSize: 13, color: "var(--chili)", fontWeight: 600 }}
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
        title="Remove entry"
        message={pendingDelete ? `Remove the ${formatWeight(pendingDelete.weightKg, unitSystem)} entry? This can't be undone.` : ""}
        confirmLabel="Remove"
        onConfirm={confirmDelete}
        onCancel={() => setPendingDelete(null)}
      />
    </div>
  );
}