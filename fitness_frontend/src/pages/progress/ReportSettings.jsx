import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import PageHeader from "../../components/PageHeader";
import { Loading, ErrorBanner, extractErrorMessage } from "../../components/Status";
import { getReportSettings, updateReportSettings } from "../../api/progress";

export default function ReportSettings() {
  const navigate = useNavigate();
  const [settings, setSettings] = useState(null);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    getReportSettings().then(setSettings).catch((err) => setError(extractErrorMessage(err)));
  }, []);

  async function handleSave() {
    setSaving(true);
    setError("");
    try {
      const updated = await updateReportSettings({
        day_interval: settings.day_interval,
        report_type: settings.report_type,
        is_enabled: settings.is_enabled,
      });
      setSettings(updated);
      navigate("/progress");
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  if (!settings) {
    return (
      <div className="page">
        <PageHeader title="Settings" back />
        <ErrorBanner message={error} />
        {!error && <Loading />}
      </div>
    );
  }

  return (
    <div className="page">
      <PageHeader title="Settings" back />
      <h3>Progress Report</h3>

      <div className="card" style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        <div>
          <label>Report interval</label>
          <div style={{ display: "flex", alignItems: "center", gap: 14, justifyContent: "center", padding: "8px 0" }}>
            <button
              className="btn btn-secondary"
              style={{ width: 40, height: 40, padding: 0 }}
              onClick={() => setSettings((s) => ({ ...s, day_interval: Math.max(1, s.day_interval - 1) }))}
              disabled={settings.day_interval <= 1}
            >
              −
            </button>
            <div style={{ textAlign: "center" }}>
              <div className="stat-lg">{settings.day_interval}</div>
              <div className="eyebrow">days</div>
            </div>
            <button
              className="btn btn-secondary"
              style={{ width: 40, height: 40, padding: 0 }}
              onClick={() => setSettings((s) => ({ ...s, day_interval: Math.min(90, s.day_interval + 1) }))}
              disabled={settings.day_interval >= 90}
            >
              +
            </button>
          </div>
        </div>

        <div>
          <label>Report type</label>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
            {[["short", "Short", "Brief overview of your progress"], ["detailed", "Detailed", "In-depth analysis with personalized feedback"]].map(([v, l, desc]) => (
              <button
                key={v}
                onClick={() => setSettings((s) => ({ ...s, report_type: v }))}
                className={settings.report_type === v ? "btn btn-primary" : "btn btn-secondary"}
                style={{ flexDirection: "column", height: "auto", padding: 12, gap: 4, alignItems: "flex-start", textAlign: "left" }}
              >
                <span style={{ fontWeight: 700 }}>{l}</span>
                <span style={{ fontSize: 11, fontWeight: 400, opacity: 0.85 }}>{desc}</span>
              </button>
            ))}
          </div>
        </div>

        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div style={{ paddingRight: 12 }}>
            <label style={{ marginBottom: 2 }}>Interval-based generation</label>
            <p style={{ fontSize: 12, color: "var(--text-faint)" }}>
              When on, a report is generated automatically once every {settings.day_interval} days
              (next time you open the app), as long as you've logged new workout or nutrition
              data since the last one. Manual generation with the button always works either way.
            </p>
          </div>
          <button
            type="button"
            role="switch"
            aria-checked={settings.is_enabled}
            className={`switch ${settings.is_enabled ? "on" : ""}`}
            onClick={() => setSettings((s) => ({ ...s, is_enabled: !s.is_enabled }))}
          />
        </div>

        <ErrorBanner message={error} />
        <button className="btn btn-primary btn-block" onClick={handleSave} disabled={saving}>
          {saving ? "Saving..." : "Save Settings"}
        </button>
      </div>
    </div>
  );
}