import { client } from "./client";

export async function listReports() {
  const { data } = await client.get("/progress/reports/");
  return data;
}

export async function getReport(id) {
  const { data } = await client.get(`/progress/reports/${id}/`);
  return data;
}

export async function deleteReport(id) {
  await client.delete(`/progress/reports/${id}/`);
}

export async function generateReport({ periodDays, reportType } = {}) {
  const { data } = await client.post("/progress/reports/generate/", {
    period_days: periodDays,
    report_type: reportType,
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
