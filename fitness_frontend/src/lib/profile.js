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