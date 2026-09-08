import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import PageHeader from "../../components/PageHeader";
import { Loading, ErrorBanner, extractErrorMessage } from "../../components/Status";
import { useToast } from "../../context/ToastContext";
import { getReport, downloadReportPdf } from "../../api/progress";

export default function ReportDetail() {
  const { id } = useParams();
  const showToast = useToast();
  const [report, setReport] = useState(null);
  const [error, setError] = useState("");
  const [downloading, setDownloading] = useState(false);

  useEffect(() => {
    getReport(id).then(setReport).catch((err) => setError(extractErrorMessage(err)));
  }, [id]);

  async function handleDownloadPdf() {
    setDownloading(true);
    try {
      await downloadReportPdf(id, `progress-report-${report.report_number}.pdf`);
    } catch (err) {
      showToast(extractErrorMessage(err, "Couldn't download the PDF."), "error");
    } finally {
      setDownloading(false);
    }
  }

  if (!report) {
    return (
      <div className="page">
        <PageHeader title="Loading" back />
        <ErrorBanner message={error} />
        {!error && <Loading />}
      </div>
    );
  }

  const recommendations = report.rule_based_insights?.overall_recommendations || [];

  return (
    <div className="page">
      <PageHeader
        title={`Report #${report.report_number}`}
        back
        subtitle={`${report.period_start} - ${report.period_end} · ${report.triggered_by === "interval" ? "Interval" : "Manual"}`}
      />

      {report.status === "failed" && (
        <ErrorBanner message={report.generation_error || "This report failed to generate."} />
      )}

      {report.status === "generated" && (
        <button className="btn btn-secondary" onClick={handleDownloadPdf} disabled={downloading} style={{ marginBottom: 12 }}>
          {downloading ? "Preparing PDF..." : "Download PDF"}
        </button>
      )}

      {report.progress_summary && (
        <Section title="Progress Summary" accent="bamboo" body={report.progress_summary} />
      )}
      {report.workout_feedback && (
        <Section title="Workout Feedback" accent="chili" body={report.workout_feedback} />
      )}
      {report.nutrition_feedback && (
        <Section title="Nutrition Feedback" accent="turmeric" body={report.nutrition_feedback} />
      )}
      {report.key_takeaways && (
        <Section title="Key Takeaways" accent="bamboo" body={report.key_takeaways} />
      )}

      {recommendations.length > 0 && (
        <div className="card">
          <h3 style={{ marginBottom: 10 }}>Recommendations</h3>
          {recommendations.map((rec, i) => (
            <div key={i} style={{ display: "flex", gap: 8, padding: "6px 0", borderTop: i > 0 ? "1px solid var(--border-soft)" : "none" }}>
              <span className={`pill ${rec.priority === "high" ? "pill-chili" : "pill-turmeric"}`} style={{ flexShrink: 0, height: "fit-content" }}>
                {rec.priority}
              </span>
              <p style={{ fontSize: 13 }}>{rec.recommendation}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function Section({ title, accent, body }) {
  return (
    <div className="card card-tab" style={{ "--accent-color": `var(--${accent})` }}>
      <h3 style={{ marginBottom: 8 }}>{title}</h3>
      <p style={{ fontSize: 14, lineHeight: 1.6, whiteSpace: "pre-wrap" }}>{body}</p>
    </div>
  );
}