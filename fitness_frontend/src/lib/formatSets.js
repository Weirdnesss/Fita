// 45 -> "45s", 65 -> "1:05"
export function formatSeconds(total) {
  const t = Math.max(0, Math.round(total || 0));
  const m = Math.floor(t / 60);
  const s = t % 60;
  return m > 0 ? `${m}:${String(s).padStart(2, "0")}` : `${s}s`;
}