import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import PageHeader from "../../components/PageHeader";
import { Loading, ErrorBanner, EmptyState, extractErrorMessage } from "../../components/Status";
import ConfirmDialog from "../../components/ConfirmDialog";
import { useToast } from "../../context/ToastContext";
import { listReports, generateReport, deleteReport, getReportSettings } from "../../api/progress";

const AUTO_GEN_BACKOFF_MS = 5 * 60 * 1000; // 5 minutes

export default function ReportsList() {
  const navigate = useNavigate();
  const showToast = useToast();
  const [reports, setReports] = useState(null);
  const [settings, setSettings] = useState(null);
  const [error, setError] = useState("");
  const [generating, setGenerating] = useState(false);
  const [autoGenerating, setAutoGenerating] = useState(false);
  const [cooldown, setCooldown] = useState(0); // seconds remaining before another generate is allowed
  const [pendingDelete, setPendingDelete] = useState(null); // report id | null
  const autoTriedRef = useRef(false); // guard against double-firing (e.g. React StrictMode)

  useEffect(() => {
    load();
    refreshSettings();
  }, []);

  useEffect(() => {
    if (cooldown <= 0) return;
    const t = setInterval(() => setCooldown((c) => Math.max(c - 1, 0)), 1000);
    return () => clearInterval(t);
  }, [cooldown]);

  // Interval-based generation: there's no server-side scheduler here, so
  // "automatic" means "check when the app is opened" -- if the user has
  // allowed it (is_enabled) and a report is due with data to report on,
  // fire it quietly in the background rather than making them tap Generate.
  //
  // autoTriedRef only guards against double-firing within THIS mount (e.g.
  // React StrictMode's double effect invocation in dev) -- it resets if the
  // user navigates away (e.g. to Settings) and back, which used to let a
  // second interval generation fire while the first was still running,
  // since due_status doesn't flip to "not_due" until the first one finishes
  // and updates last_generated_at. sessionStorage survives that navigation,
  // so we don't even attempt a second request; the backend's own
  // generation_started_at lock is the real backstop if this is ever bypassed
  // (e.g. two tabs open at once).
  useEffect(() => {
    if (!settings || autoTriedRef.current) return;
    if (settings.due_status !== "due") return;
    const sessionKey = `progress_auto_gen_tried_${settings.last_generated_at || "never"}`;
    if (sessionStorage.getItem(sessionKey)) return;

    const backoffUntil = Number(sessionStorage.getItem("progress_auto_gen_backoff_until") || 0);
    if (Date.now() < backoffUntil) return;

    autoTriedRef.current = true;
    runIntervalGeneration(sessionKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [settings]);

  function load() {
    listReports().then(setReports).catch((err) => setError(extractErrorMessage(err)));
  }

  function refreshSettings() {
    getReportSettings().then(setSettings).catch(() => {}); // due-banner is a nice-to-have, fail silently
  }

  async function runIntervalGeneration(sessionKey) {
    setAutoGenerating(true);
    try {
      const report = await generateReport({ triggeredBy: "interval" });
      if (report.status === "failed") {
        // Failed, but don't mark this generation as "tried" permanently --
        // back off for 5 minutes instead, so it can retry on a later visit
        // rather than staying silently blocked for the rest of the session.
        sessionStorage.setItem("progress_auto_gen_backoff_until", String(Date.now() + AUTO_GEN_BACKOFF_MS));
        showToast("Automatic report generation failed -- will retry later", "error");
        return;
      }
      // Only permanently suppress retries for this last_generated_at once we
      // actually succeed.
      sessionStorage.setItem(sessionKey, "1");
      showToast("New interval report generated", "success");
      load();
      refreshSettings();
    } catch {
      sessionStorage.setItem("progress_auto_gen_backoff_until", String(Date.now() + AUTO_GEN_BACKOFF_MS));
      showToast("Automatic report generation failed -- will retry later", "error");
    } finally {
      setAutoGenerating(false);
    }
  }

  async function handleGenerate() {
    setGenerating(true);
    setError("");
    try {
      // No periodDays/reportType passed -- the backend falls back to the
      // user's own settings (day_interval/report_type) when omitted.
      const report = await generateReport({ triggeredBy: "manual" });
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
      refreshSettings();
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

      {autoGenerating && (
        <div className="card card-tab" style={{ "--accent-color": "var(--bamboo)" }}>
          <p style={{ fontSize: 13, color: "var(--text-faint)" }}>Generating your interval report...</p>
        </div>
      )}
      {!autoGenerating && settings?.due_status === "due" && (
        <div className="card card-tab" style={{ "--accent-color": "var(--turmeric)" }}>
          <p style={{ fontSize: 13 }}>
            <span className="pill pill-turmeric" style={{ marginRight: 8 }}>Due</span>
            {settings.last_generated_at
              ? `It's been ${settings.day_interval}+ days since your last report.`
              : "You haven't generated a report yet."}
          </p>
        </div>
      )}
      {settings?.due_status === "due_no_data" && (
        <div className="card card-tab" style={{ "--accent-color": "var(--border)" }}>
          <p style={{ fontSize: 13, color: "var(--text-faint)" }}>
            You have no workout or food history logged -- it's not recommended to
            generate a report right now.
          </p>
        </div>
      )}

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
            <p style={{ fontWeight: 600 }}>Report #{r.report_number}</p>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <TriggeredByPill triggeredBy={r.triggered_by} />
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
        message={
          pendingDelete !== null
            ? `Delete Report #${reports?.find((r) => r.id === pendingDelete)?.report_number ?? ""}? This can't be undone.`
            : ""
        }
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

function TriggeredByPill({ triggeredBy }) {
  if (!triggeredBy) return null;
  return (
    <span className="pill" style={{ background: "var(--bg-raised)", color: "var(--text-faint)" }}>
      {triggeredBy === "interval" ? "Interval" : "Manual"}
    </span>
  );
}