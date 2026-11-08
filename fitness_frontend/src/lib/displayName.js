// Shortens database food names for display only (the stored name is unchanged).
// Brand names and USDA program notes mean nothing to users. Add to BRANDS as new ones turn up.
const BRANDS = ["Vitasoy USA Organic Nasoya", "Vitasoy USA, Nasoya", "Vitasoy USA", "Organic Nasoya", "Nasoya", "MORI-NU", "CHOBANI"];

const escape = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const BRAND_RE = new RegExp(`(^|,\\s*|\\s+)(${BRANDS.map(escape).join("|")})(?=,|\\s|$)`, "gi");

export default function displayName(name) {
  if (!name) return "";
  let n = name
    .replace(/\s*\(Includes foods for USDA'?s? [^)]*\)/gi, "")
    .replace(BRAND_RE, "")
    .replace(/\s{2,}/g, " ")
    .replace(/^[\s,]+|[\s,]+$/g, "")
    .replace(/,\s*,/g, ",");
  // "Lite Firm Tofu" / "Soft Tofu" -> "Tofu, lite firm" / "Tofu, soft"
  const m = n.match(/^(.*?)\s*,?\s*\b(Tofu)\b$/i);
  if (m && m[1]) n = `Tofu, ${m[1].replace(/^[\s,]+|[\s,]+$/g, "").toLowerCase()}`;
  const t = n.match(/^(.*),\s*Tofu$/i);
  if (t) n = `Tofu, ${t[1].trim().toLowerCase()}`;
  return n.charAt(0).toUpperCase() + n.slice(1);
}