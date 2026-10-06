function parseDate(value) {
  // date-only strings need a time added or some timezones show the day before
  return new Date(value.length === 10 ? `${value}T00:00:00` : value);
}

// Returns null when automatic reports are off, otherwise
// { kind: "waiting" | "due" | "scheduled", text }
export function nextReportInfo(settings) {
  if (!settings || !settings.is_enabled) return null;

  if (settings.has_new_data === false || settings.due_status === "due_no_data") {
    return { kind: "waiting", text: "Waiting for data" };
  }
  if (settings.due_status === "due") {
    return { kind: "due", text: "Due now" };
  }
  if (!settings.next_generation_date) return null;

  const text = parseDate(settings.next_generation_date).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
  });
  return { kind: "scheduled", text };
}