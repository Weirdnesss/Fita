import { client } from "./client";

export async function listReports() {
  const { data } = await client.get("/progress/reports/");
  return data;
}

export async function getReport(id) {
  const { data } = await client.get(`/progress/reports/${id}/`);
  return data;
}

export async function downloadReportPdf(id, filename) {
  try {
    const { data } = await client.get(`/progress/reports/${id}/pdf/`, { responseType: "blob" });
    const url = URL.createObjectURL(data);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename || `progress-report-${id}.pdf`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  } catch (err) {
    // With responseType: "blob", axios doesn't parse an error response
    // body as JSON -- it arrives as a raw Blob, which breaks
    // extractErrorMessage. Re-parse it so callers still get a real message.
    if (err.response?.data instanceof Blob) {
      const text = await err.response.data.text();
      try {
        err.response.data = JSON.parse(text);
      } catch {
        err.response.data = text;
      }
    }
    throw err;
  }
}

export async function deleteReport(id) {
  await client.delete(`/progress/reports/${id}/`);
}

export async function generateReport({ periodDays, reportType, triggeredBy = "manual" } = {}) {
  const { data } = await client.post("/progress/reports/generate/", {
    period_days: periodDays,
    report_type: reportType,
    triggered_by: triggeredBy,
  });
  return data;
}

export async function getReportSettings() {
  const { data } = await client.get("/progress/settings/");
  return data;
}

export async function updateReportSettings(fields) {
  const { data } = await client.patch("/progress/settings/", fields);
  return data;
}