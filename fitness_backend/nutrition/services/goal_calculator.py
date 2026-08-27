"""
Calculates suggested daily calorie and macro goals from a user's Profile,
using the Mifflin-St Jeor equation (the formula most current nutrition
science guidelines recommend over the older Harris-Benedict one).

This is a deterministic formula, not an LLM call -- on purpose. Precise
numeric health estimates should be reproducible and explainable, which
is exactly what a fixed formula gives you and an LLM does not.

    BMR (kcal/day):
        Male:   10*weight_kg + 6.25*height_cm - 5*age + 5
        Female: 10*weight_kg + 6.25*height_cm - 5*age - 161
        Other/unspecified: average of the two, a common neutral default
        when a formula requires a sex-linked constant but the person
        hasn't specified one.

    TDEE = BMR x activity multiplier (Sedentary 1.2 up to Very Active 1.725)

    Calorie target = TDEE, adjusted by goal:
        lose_weight              TDEE - 500  (~0.5 kg/week deficit)
        gain_weight / gain_muscle TDEE + 350  (lean surplus)
        build_strength / maintain TDEE

Safety floors: never suggests below 1500 kcal (male) / 1200 kcal (female)
regardless of the computed deficit -- these are widely-cited clinical
minimums for adults, not to be crossed by an automated estimate.

Macros: protein set by bodyweight (higher for cutting/muscle goals, to
preserve lean mass), fat as a % of calories that also varies by goal
(lower for muscle/strength to prioritize carbs, higher for weight gain),
carbs fill the rest.
"""

from dataclasses import dataclass

ACTIVITY_MULTIPLIERS = {
    "sedentary": 1.2,
    "lightly_active": 1.375,
    "moderately_active": 1.55,
    "very_active": 1.725,
}

GOAL_CALORIE_ADJUSTMENT = {
    "lose_weight": -500,
    "gain_weight": 350,
    "gain_muscle": 350,
    "build_strength": 0,
    "maintain_weight": 0,
}

# g of protein per kg of bodyweight -- higher for cutting/building goals to
# help preserve/build lean mass, per standard sports-nutrition guidance.
PROTEIN_G_PER_KG = {
    "lose_weight": 2.0,
    "gain_muscle": 1.8,
    "build_strength": 1.8,
    "gain_weight": 1.6,
    "maintain_weight": 1.6,
}

# Fat as a % of total calories, varied by goal:
#   - Muscle/strength goals lean lower-fat to free up carbs for training
#     performance and glycogen replenishment, which matter more for those
#     goals than extra dietary fat does.
#   - A weight-gain goal leans higher-fat since it's calorically denser --
#     easier to hit a surplus without needing a lot of food volume.
#   - Lose/maintain stay at a balanced 25% (moderate fat aids satiety
#     during a deficit).
FAT_PCT_OF_CALORIES = {
    "lose_weight": 0.25,
    "maintain_weight": 0.25,
    "gain_muscle": 0.20,
    "build_strength": 0.20,
    "gain_weight": 0.30,
}

MIN_SAFE_CALORIES = {"male": 1500, "female": 1200}
DEFAULT_MIN_SAFE_CALORIES = 1350  # used for "other" / unspecified gender

REQUIRED_FIELDS = ["current_weight_kg", "height_cm", "age", "gender"]


@dataclass
class GoalCalculationResult:
    calories: float
    protein_g: float
    carbs_g: float
    fat_g: float
    bmr: float
    tdee: float
    calorie_floor_applied: bool
    assumptions: list[str]


def missing_profile_fields(profile):
    """Returns the subset of REQUIRED_FIELDS that profile doesn't have set."""
    missing = []
    for field in REQUIRED_FIELDS:
        value = getattr(profile, field, None)
        if value in (None, ""):
            missing.append(field)
    return missing


def calculate_goals(profile) -> GoalCalculationResult:
    """
    Computes suggested daily calorie/macro goals for a Profile.
    Raises ValueError if a required field (weight, height, age, gender)
    is missing -- check missing_profile_fields() first to give the user
    a friendly prompt instead of catching this.
    """
    missing = missing_profile_fields(profile)
    if missing:
        raise ValueError(f"Missing required profile fields: {', '.join(missing)}")

    weight_kg = profile.current_weight_kg
    height_cm = profile.height_cm
    age = profile.age
    gender = profile.gender

    assumptions = []

    if gender == "male":
        bmr = 10 * weight_kg + 6.25 * height_cm - 5 * age + 5
    elif gender == "female":
        bmr = 10 * weight_kg + 6.25 * height_cm - 5 * age - 161
    else:
        bmr_male = 10 * weight_kg + 6.25 * height_cm - 5 * age + 5
        bmr_female = 10 * weight_kg + 6.25 * height_cm - 5 * age - 161
        bmr = (bmr_male + bmr_female) / 2
        assumptions.append(
            "Used an average of the male/female BMR formulas since gender wasn't male or female."
        )

    activity_level = profile.activity_level or "sedentary"
    if not profile.activity_level:
        assumptions.append("No activity level set -- assumed Sedentary.")
    multiplier = ACTIVITY_MULTIPLIERS[activity_level]
    tdee = bmr * multiplier

    goal = profile.primary_goal or "maintain_weight"
    if not profile.primary_goal:
        assumptions.append("No primary goal set -- assumed Maintain Weight.")
    calories = tdee + GOAL_CALORIE_ADJUSTMENT[goal]

    calorie_floor = MIN_SAFE_CALORIES.get(gender, DEFAULT_MIN_SAFE_CALORIES)
    calorie_floor_applied = calories < calorie_floor
    if calorie_floor_applied:
        calories = calorie_floor
        assumptions.append(
            f"Calculated deficit went below a safe minimum, so calories were capped at {calorie_floor} kcal."
        )

    protein_g = PROTEIN_G_PER_KG[goal] * weight_kg
    protein_kcal = protein_g * 4
    fat_kcal = calories * FAT_PCT_OF_CALORIES[goal]
    fat_g = fat_kcal / 9
    carbs_kcal = max(calories - protein_kcal - fat_kcal, 0)
    carbs_g = carbs_kcal / 4

    return GoalCalculationResult(
        calories=round(calories),
        protein_g=round(protein_g),
        carbs_g=round(carbs_g),
        fat_g=round(fat_g),
        bmr=round(bmr),
        tdee=round(tdee),
        calorie_floor_applied=calorie_floor_applied,
        assumptions=assumptions,
    )
