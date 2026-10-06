import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import PageHeader from "../../components/PageHeader";
import { Loading, ErrorBanner, EmptyState, extractErrorMessage } from "../../components/Status";
import ConfirmDialog from "../../components/ConfirmDialog";
import { useToast } from "../../context/ToastContext";
import { listReports, generateReport, deleteReport, getReportSettings, REPORT_FAILURE_MESSAGE } from "../../api/progress";
import SettingsButton from "../../components/SettingsButton";
import { nextReportInfo } from "../../lib/reports";

const REPORTS_PAGE_SIZE = 10;

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
  const [visibleCount, setVisibleCount] = useState(REPORTS_PAGE_SIZE);
  const noData = settings?.has_new_data === false;
  const nextReport = nextReportInfo(settings);

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
    autoTriedRef.current = true;
    sessionStorage.setItem(sessionKey, "1");
    runIntervalGeneration();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [settings]);

  function load() {
    listReports().then(setReports).catch((err) => setError(extractErrorMessage(err)));
  }

  function refreshSettings() {
    getReportSettings().then(setSettings).catch(() => {}); // due-banner is a nice-to-have, fail silently
  }

  async function runIntervalGeneration() {
    setAutoGenerating(true);
    try {
      const report = await generateReport({ triggeredBy: "interval" });
      if (report.status === "failed") {
        // Still quiet -- no toast/banner, since the user didn't ask for
        // this one -- but the list must still reflect it, or a failed
        // interval report silently disappears until an unrelated reload.
        return;
      }
      showToast("New interval report generated", "success");
    } catch {
      // Same reasoning -- fail silently for an automatic trigger.
    } finally {
      setAutoGenerating(false);
      load();
      refreshSettings();
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
        setError(report.generation_error || REPORT_FAILURE_MESSAGE);
      } else {
        showToast("Report generated", "success");
        navigate(`/progress/${report.id}`);
      }
    } catch (err) {
      if (err.response?.status === 429) {
        setCooldown(err.response.data.retry_after_seconds || 60);
      }
      setError(extractErrorMessage(err, "Couldn't generate a report -- check your connection and that you have logged data."));
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

  const latest = reports?.find((r) => r.status === "generated");
  const previous = reports ? reports.filter((r) => r !== latest) : [];
  const visiblePrevious = previous.slice(0, visibleCount);

  return (
    <div className="page">
      <PageHeader
        title="Progress Reports"
        subtitle="Generated Reports"
        action={<SettingsButton to="/progress/settings" label="Report settings" />}
      />
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
      {noData && (
        <div className="card card-tab" style={{ "--accent-color": "var(--border)" }}>
          <p style={{ fontSize: 13, color: "var(--text-faint)" }}>
            Nothing logged in the last {settings.day_interval} days, so there's nothing to report on yet.
            Log a workout or a meal to enable reports.
          </p>
        </div>
      )}

      <div className="page-actions">
        <button
          className="btn btn-primary btn-block"
          onClick={handleGenerate}
          disabled={generating || autoGenerating || cooldown > 0 || noData}
        >
          {generating ? "Generating..." : cooldown > 0 ? `Try again in ${cooldown}s` : "Generate Report"}
        </button>
      </div>
      {nextReport?.kind === "scheduled" && (
        <p style={{ fontSize: 12, color: "var(--text-faint)", textAlign: "right" }}>
          Next automatic report due {nextReport.text}
        </p>
      )}

      {reports === null && <Loading />}
      {reports?.length === 0 && <EmptyState title="No reports yet" eyebrow="Generate your first one above" />}

      {latest && (
        <>
          <h3>Latest Report</h3>
          <ReportCard
            r={latest}
            featured
            onOpen={() => navigate(`/progress/${latest.id}`)}
            onDelete={() => setPendingDelete(latest.id)}
          />
        </>
      )}
      {previous.length > 0 && (
        <>
          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <h3>Previous Reports</h3>
            <span style={{ fontSize: 12, color: "var(--text-faint)" }}>{previous.length} reports</span>
          </div>

          <div className="report-list-grid">
            {visiblePrevious.map((r) => (
              <ReportCard
                key={r.id}
                r={r}
                onOpen={() => navigate(`/progress/${r.id}`)}
                onDelete={() => setPendingDelete(r.id)}
              />
            ))}
          </div>
        </>
      )}

      {previous.length > visibleCount && (
        <button
          className="btn btn-secondary"
          style={{ width: "100%", marginTop: 4 }}
          onClick={() => setVisibleCount((c) => c + REPORTS_PAGE_SIZE)}
        >
          Load More ({previous.length - visibleCount} left)
        </button>
      )}

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
  if (status === "generated") return null; // the default/expected state doesn't need a badge
  const map = {
    pending: "pill-turmeric",
    failed: "pill-chili",
  };
  return <span className={`pill ${map[status] || "pill-chili"}`}>{status}</span>;
}

function TriggeredByPill({ triggeredBy }) {
  if (!triggeredBy) return null;
  const isInterval = triggeredBy === "interval";
  return (
    <span className={`pill ${isInterval ? "pill-ube" : "pill-bamboo"}`}>
      {isInterval ? "Interval" : "Manual"}
    </span>
  );
}

function ReportCard({ r, onOpen, onDelete, featured = false }) {
  const previewLength = featured ? 280 : 120;
  return (
    <div
      className="card card-tab"
      style={{
        marginBottom: featured ? 0 : 10,
        cursor: "pointer",
        "--accent-color": r.triggered_by === "interval" ? "var(--ube)" : "var(--bamboo)",
      }}
      onClick={onOpen}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
        <p style={{ fontWeight: 600 }}>Report #{r.report_number}</p>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <TriggeredByPill triggeredBy={r.triggered_by} />
          <StatusPill status={r.status} />
          <button
            className="btn-ghost"
            onClick={(e) => { e.stopPropagation(); onDelete(); }}
          >
            Delete
          </button>
        </div>
      </div>
      <p style={{ fontSize: 12, color: "var(--text-faint)", marginBottom: 6 }}>
        {r.period_start} - {r.period_end}
      </p>
      {r.progress_summary ? (
        <p style={{ fontSize: 13, color: "var(--text-dim)" }}>
          {r.progress_summary.slice(0, previewLength)}
          {r.progress_summary.length > previewLength ? "..." : ""}
        </p>
      ) : r.status === "failed" ? (
        <p style={{ fontSize: 13, color: "var(--chili)" }}>
          {r.generation_error || REPORT_FAILURE_MESSAGE}
        </p>
      ) : null}
    </div>
  );
}