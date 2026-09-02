import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import PageHeader from "../../components/PageHeader";
import { Loading, ErrorBanner, EmptyState, extractErrorMessage } from "../../components/Status";
import ConfirmDialog from "../../components/ConfirmDialog";
import { useToast } from "../../context/ToastContext";
import { listReports, generateReport, deleteReport } from "../../api/progress";

export default function ReportsList() {
  const navigate = useNavigate();
  const showToast = useToast();
  const [reports, setReports] = useState(null);
  const [error, setError] = useState("");
  const [generating, setGenerating] = useState(false);
  const [cooldown, setCooldown] = useState(0); // seconds remaining before another generate is allowed
  const [pendingDelete, setPendingDelete] = useState(null); // report id | null

  useEffect(() => {
    load();
  }, []);

  useEffect(() => {
    if (cooldown <= 0) return;
    const t = setInterval(() => setCooldown((c) => Math.max(c - 1, 0)), 1000);
    return () => clearInterval(t);
  }, [cooldown]);

  function load() {
    listReports().then(setReports).catch((err) => setError(extractErrorMessage(err)));
  }

  async function handleGenerate() {
    setGenerating(true);
    setError("");
    try {
      const report = await generateReport({ periodDays: 7, reportType: "short" });
      if (report.status === "failed") {
        setError(report.generation_error || "Report generation failed.");
      } else {
        navigate(`/progress/${report.id}`);
      }
    } catch (err) {
      if (err.response?.status === 429) {
        setCooldown(err.response.data.retry_after_seconds || 60);
      }
      setError(extractErrorMessage(err, "Couldn't generate a report -- check GROQ_API_KEY and that you have logged data."));
    } finally {
      setGenerating(false);
      load();
    }
  }

  async function confirmDeleteReport() {
    const id = pendingDelete;
    setPendingDelete(null);
    try {
      await deleteReport(id);
      setReports((rs) => rs.filter((r) => r.id !== id));
      showToast("Report deleted", "success");
    } catch (err) {
      showToast(extractErrorMessage(err), "error");
    }
  }

  return (
    <div className="page">
      <PageHeader title="Progress Reports" subtitle="Generated Reports" />
      <ErrorBanner message={error} />

      <div style={{ display: "flex", gap: 8 }}>
        <button className="btn btn-primary" style={{ flex: 1 }} onClick={handleGenerate} disabled={generating || cooldown > 0}>
          {generating ? "Generating..." : cooldown > 0 ? `Wait ${cooldown}s` : "Generate New Report"}
        </button>
        <button className="btn btn-secondary" onClick={() => navigate("/progress/settings")}>
          Settings
        </button>
      </div>

      {reports === null && <Loading />}
      {reports?.length === 0 && <EmptyState title="No reports yet" eyebrow="Generate your first one above" />}
      {reports?.map((r) => (
        <div key={r.id} className="card card-tab" style={{ marginBottom: 10, cursor: "pointer" }} onClick={() => navigate(`/progress/${r.id}`)}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
            <p style={{ fontWeight: 600 }}>Report #{r.id}</p>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <StatusPill status={r.status} />
              <button
                onClick={(e) => { e.stopPropagation(); setPendingDelete(r.id); }}
                style={{ background: "none", border: "none", color: "var(--text-faint)", fontSize: 12 }}
              >
                Delete
              </button>
            </div>
          </div>
          <p style={{ fontSize: 12, color: "var(--text-faint)", marginBottom: 6 }}>
            {r.period_start} - {r.period_end}
          </p>
          {r.progress_summary && (
            <p style={{ fontSize: 13, color: "var(--text-dim)" }}>
              {r.progress_summary.slice(0, 120)}{r.progress_summary.length > 120 ? "..." : ""}
            </p>
          )}
        </div>
      ))}

      <ConfirmDialog
        open={pendingDelete !== null}
        title="Delete report"
        message={pendingDelete !== null ? `Delete Report #${pendingDelete}? This can't be undone.` : ""}
        confirmLabel="Delete"
        onConfirm={confirmDeleteReport}
        onCancel={() => setPendingDelete(null)}
      />
    </div>
  );
}

function StatusPill({ status }) {
  const map = {
    generated: "pill-bamboo",
    pending: "pill-turmeric",
    failed: "pill-chili",
  };
  return <span className={`pill ${map[status] || "pill-chili"}`}>{status}</span>;
}
