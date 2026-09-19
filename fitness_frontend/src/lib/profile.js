// Fields collected across Signup Steps 2 & 3 (see Signup.jsx / EditProfile.jsx).
// current_weight_kg is deliberately not included -- it isn't a profile
// field the user fills in directly, it's set by logging a weight entry
// on /profile itself, so it doesn't belong in an "incomplete profile"
// check the same way.
export const REQUIRED_PROFILE_FIELDS = [
  "gender",
  "date_of_birth",
  "activity_level",
  "goal_weight_kg",
  "height_ft",
  "height_in",
  "primary_goal",
  "workout_frequency",
  "workout_location",
];

export function isProfileIncomplete(profile) {
  if (!profile) return true;
  return REQUIRED_PROFILE_FIELDS.some(
    (field) => profile[field] === null || profile[field] === undefined || profile[field] === ""
  );
}

// Height is stored server-side as height_ft/height_in (see
// accounts/models.py) -- height_cm is only a derived read-only field
// for display/BMI. Offering a cm input is a frontend-only convenience:
// convert to ft/in right before submitting, so the API contract never
// has to change.
export function cmToFtIn(cm) {
  const totalInches = cm / 2.54;
  const ft = Math.floor(totalInches / 12);
  const inch = Math.round(totalInches - ft * 12);
  // Rounding inches up to 12 (e.g. 71.6in -> 5ft 12in) should roll
  // into the next foot instead.
  if (inch === 12) return { ft: ft + 1, inch: 0 };
  return { ft, inch };
}

export function ftInToCm(ft, inch) {
  const totalInches = Number(ft || 0) * 12 + Number(inch || 0);
  return Math.round(totalInches * 2.54);
}

// Same story as height: current_weight_kg/goal_weight_kg/weight_kg are
// the only fields the backend stores or accepts (see accounts/models.py
// -- no lbs field exists anywhere server-side). lbs is a frontend-only
// input convenience, converted to kg before it ever reaches the API.
const KG_PER_LB = 0.45359237;

export function kgToLbs(kg) {
  return Math.round((kg / KG_PER_LB) * 10) / 10;
}

export function lbsToKg(lbs) {
  return Math.round(lbs * KG_PER_LB * 10) / 10;
}

// Read-only display formatting, driven by profile.unit_system (see
// accounts/models.py UnitSystem -- "metric" or "imperial"). Storage is
// unaffected either way; this only decides how a stored kg/ft/in value
// is *shown*. Defaults to metric so callers that don't have a logged-in
// profile yet (or an older profile predating this field) still get a
// sensible fallback.
export function formatWeight(kg, unitSystem = "metric") {
  if (kg === null || kg === undefined || kg === "") return null;
  if (unitSystem === "imperial") return `${Math.round(kgToLbs(Number(kg)))} lbs`;
  return `${Number(kg)} kg`;
}

export function formatHeight(ft, inch, unitSystem = "metric") {
  if (ft === null || ft === undefined || ft === "") return null;
  if (unitSystem === "imperial") return `${ft}' ${inch || 0}"`;
  return `${ftInToCm(ft, inch)} cm`;
}

// For a +/- change value (e.g. weight trend delta) rather than an
// absolute reading -- kept separate from formatWeight so callers don't
// have to strip/re-add the sign themselves.
export function formatWeightDelta(kgChange, unitSystem = "metric") {
  if (unitSystem === "imperial") {
    return { value: Math.round(kgToLbs(kgChange)), unit: "lbs" };
  }
  return { value: Math.round(kgChange * 10) / 10, unit: "kg" };
}