import { useEffect, useState } from "react";
import { useAuth } from "../context/AuthContext";
import { logWeight, listWeightLogs, deleteWeightLog } from "../api/accounts";
import PageHeader from "../components/PageHeader";
import { Loading, ErrorBanner, extractErrorMessage } from "../components/Status";

const todayStr = () => new Date().toISOString().split("T")[0];

export default function WeightLog() {
  const { refreshUser } = useAuth();
  const [logs, setLogs] = useState(null);
  const [weightKg, setWeightKg] = useState("");
  const [loggedAt, setLoggedAt] = useState(todayStr());
  const [saving, setSaving] = useState(false);
  const [deletingId, setDeletingId] = useState(null);
  const [error, setError] = useState("");

  async function load() {
    try {
      setLogs(await listWeightLogs());
    } catch (err) {
      setError(extractErrorMessage(err, "Couldn't load weight history."));
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function handleSubmit(e) {
    e.preventDefault();
    if (weightKg === "") return;
    setError("");
    setSaving(true);
    try {
      await logWeight({ weightKg: Number(weightKg), loggedAt });
      setWeightKg("");
      setLoggedAt(todayStr());
      await load();
      // So Profile / Edit Profile show the new current_weight_kg
      // immediately instead of the stale copy AuthContext last loaded.
      await refreshUser();
    } catch (err) {
      setError(extractErrorMessage(err, "Couldn't log that weight."));
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(id) {
    setDeletingId(id);
    setError("");
    try {
      await deleteWeightLog(id);
      await load();
      await refreshUser();
    } catch (err) {
      setError(extractErrorMessage(err, "Couldn't delete that entry."));
    } finally {
      setDeletingId(null);
    }
  }

  return (
    <div className="page">
      <PageHeader title="Log Weight" back backTo="/profile/edit" />

      <form onSubmit={handleSubmit} className="card" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
          <div>
            <label>Weight (kg)</label>
            <input type="number" step="0.1" required value={weightKg} onChange={(e) => setWeightKg(e.target.value)} placeholder="e.g. 78.5" />
          </div>
          <div>
            <label>Date</label>
            <input type="date" max={todayStr()} value={loggedAt} onChange={(e) => setLoggedAt(e.target.value)} />
          </div>
        </div>
        <p style={{ fontSize: 12, color: "var(--text-faint)" }}>
          Logging again for a date you've already logged updates that entry instead of adding a duplicate.
        </p>
        <ErrorBanner message={error} />
        <button className="btn btn-primary" disabled={saving}>{saving ? "Saving..." : "Log Weight"}</button>
      </form>

      <div className="card">
        <h3 style={{ marginBottom: 10 }}>History</h3>
        {logs === null && <Loading />}
        {logs !== null && logs.length === 0 && (
          <p style={{ fontSize: 13, color: "var(--text-faint)" }}>No entries yet -- log your first weight above.</p>
        )}
        {logs?.map((entry) => (
          <div key={entry.id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "8px 0", borderBottom: "1px solid var(--border)" }}>
            <div>
              <p style={{ fontWeight: 600, fontSize: 14 }}>{entry.weight_kg} kg</p>
              <p style={{ fontSize: 12, color: "var(--text-faint)" }}>{entry.logged_at}</p>
            </div>
            <button
              className="btn-ghost"
              style={{ background: "none", border: "none", color: "var(--chili)", fontSize: 12, padding: 6 }}
              onClick={() => handleDelete(entry.id)}
              disabled={deletingId === entry.id}
            >
              {deletingId === entry.id ? "Removing..." : "Remove"}
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}