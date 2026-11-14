"""
Review packet for dietitian / adviser validation of the calorie and macro goal calculator
and the food database (the nutrition features that remain after food suggestions were switched off).

Reviewers sign off on RULES and DATA, not on individual outputs. Everything is read from the live
code, so the documents cannot drift from what the app does:

  rules.md           every formula and number the goal calculator uses, with a fingerprint to cite
  sample_goals.csv   goals calculated for a grid of body types, ages, sexes, activity levels and goals,
                     with an independent sanity audit of each (flags column)
  foods_to_check.csv foods that cite no published table, most-logged first, with verdict columns to fill in
  coach_rules.md     the chat coach's system prompt and pain guard, as shipped
  review_form.md     a sign-off form for the reviewer
  summary.md         counts, flags and the fingerprint, on one page

Nothing is written to the database.
"""

import csv
import hashlib
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

from django.db.models import Count
from django.utils import timezone

from nutrition.models import FoodItem
from nutrition.services import goal_calculator as gc

GENDERS = ("male", "female", "other")
AGES = (16, 25, 45)
BUILDS = (("small", 55, 160), ("average", 70, 170), ("heavy", 95, 175))  # name, kg, cm
ACTIVITIES = ("sedentary", "moderately_active")
GOALS = ("lose_weight", "gain_weight", "maintain_weight", "gain_muscle", "build_strength")

# Audit thresholds, deliberately independent of the calculator's own checks.
KCAL_TOLERANCE = 0.03
MACRO_KCAL_TOLERANCE = 0.40
MIN_KCAL_TO_CHECK = 50
MAX_PROTEIN_G_PER_KG = 2.0
FAT_PCT_RANGE = (0.15, 0.35)

SAMPLE_COLUMNS = [
    "scenario", "sex", "age", "build", "weight_kg", "height_cm", "activity", "goal", "bmr", "tdee",
    "calories", "protein_g", "carbs_g", "fat_g", "kcal_vs_tdee", "protein_pct", "carbs_pct", "fat_pct",
    "protein_g_per_kg", "notes", "flags",
]
FOOD_COLUMNS = [
    "id", "name", "local_name", "category", "serving_description", "serving_size_g", "kcal",
    "protein_g", "carbs_g", "fat_g", "kcal_from_macros", "macros_vs_kcal", "source", "times_logged",
    "reviewer_verdict (ok / change / remove)", "corrected_values_or_source", "reviewer_notes",
]


@dataclass
class Packet:
    rules_md: str
    fingerprint: str
    sample_rows: list
    food_rows: list
    coach_md: str
    form_md: str
    summary_md: str
    stats: dict


def _label(value):
    return str(value).replace("_", " ")


def build_rules_md():
    """Returns (markdown, fingerprint). The fingerprint covers the rules only, not the date."""
    L = []
    add = L.append
    add("# Calorie and macro goal calculator: rules for review")
    add("")
    add("Every value is read from the running code. This is a fixed formula, not a language model, so the same profile always gives the same goals.")
    add("")
    add("## 1. Energy needs")
    add("")
    add("Basal metabolic rate (BMR) uses the Mifflin-St Jeor equation:")
    add("")
    add("- Male: 10 x weight (kg) + 6.25 x height (cm) - 5 x age + 5")
    add("- Female: 10 x weight (kg) + 6.25 x height (cm) - 5 x age - 161")
    add("- Other or unspecified: the average of the two")
    add("")
    add("Daily energy use (TDEE) = BMR x activity multiplier x beginner factor.")
    add("")
    add("| Activity level | Multiplier |")
    add("|---|---|")
    for k, v in gc.ACTIVITY_MULTIPLIERS.items():
        add(f"| {_label(k).title()} | {v} |")
    add("")
    add(f"Beginner factor: {gc.BEGINNER_TDEE_FACTOR} (a flat reduction, because the formula and activity multipliers tend to overestimate and beginners often overrate their activity). No activity level on file is treated as Sedentary.")
    add("")
    add("## 2. Calorie target by goal")
    add("")
    add("| Goal | Adjustment to TDEE (kcal) |")
    add("|---|---|")
    for k, v in gc.GOAL_CALORIE_ADJUSTMENT.items():
        add(f"| {_label(k).title()} | {v:+d} |")
    add("")
    add(f"- A weight-loss deficit is limited to {round(gc.MAX_DEFICIT_FRACTION * 100)}% of TDEE, so it is never more than the 500 kcal shown.")
    add(f"- Users under {gc.ADULT_MIN_AGE} never get an automatic deficit, and are told the formulas are designed for adults and to check with a doctor or dietitian.")
    floors = ", ".join(f"{k}: {v} kcal" for k, v in gc.MIN_SAFE_CALORIES.items())
    add(f"- Calorie floors, never to be crossed: {floors}; other or unspecified: {gc.DEFAULT_MIN_SAFE_CALORIES} kcal.")
    add("- No primary goal on file is treated as Maintain Weight.")
    add("")
    add("## 3. Macronutrient targets")
    add("")
    add("| Goal | Protein (g per kg) | Fat (% of calories) |")
    add("|---|---|---|")
    for k in gc.GOAL_CALORIE_ADJUSTMENT:
        add(f"| {_label(k).title()} | {gc.PROTEIN_G_PER_KG[k]} | {round(gc.FAT_PCT_OF_CALORIES[k] * 100)}% |")
    add("")
    add(f"- Protein is calculated from the lower of actual weight and the weight at BMI {gc.PROTEIN_BASIS_BMI}, so a heavier beginner's target is not inflated by body fat.")
    add(f"- Protein is capped at {round(gc.MAX_PROTEIN_CALORIE_FRACTION * 100)}% of calories.")
    add("- Carbohydrate fills the remaining calories (never below 0 g).")
    add("")
    add("## 4. When goals are recalculated")
    add("")
    add("- Required profile fields: " + ", ".join(gc.REQUIRED_FIELDS) + ". Without them no goals are suggested.")
    add("- Goals recalculate when a new weight is logged or the profile changes, only while the user's auto-recalculate setting is on. Turning it off stops automatic changes; the user can also type their own goals.")
    add("- Each result lists the assumptions it made (for example a missing activity level, a deficit limit or a protein cap) in plain language.")
    add("")
    add("## 5. Limits")
    add("")
    add("The goals are general guidance for healthy adult gym beginners, not medical or clinical advice. The calculator does not account for medical conditions, pregnancy, or eating-disorder history.")
    body = "\n".join(L)
    return body, hashlib.sha256(body.encode()).hexdigest()[:12]


def _kcal_from_macros(protein, carbs, fat):
    return protein * 4 + carbs * 4 + fat * 9


def macros_match_kcal(kcal, protein, carbs, fat):
    if kcal < MIN_KCAL_TO_CHECK:
        return True
    return abs(_kcal_from_macros(protein, carbs, fat) - kcal) / kcal <= MACRO_KCAL_TOLERANCE


def audit_goals(profile, result):
    """Independent sanity checks on one calculated result. Returns a list of flag strings."""
    flags = []
    floor = {"male": 1500, "female": 1200}.get(profile.gender, 1350)
    if profile.age >= 18 and result.calories < floor:
        flags.append(f"below calorie floor ({floor})")
    if result.tdee and result.calories < result.tdee * 0.78 and profile.age >= 18 and not result.calorie_floor_applied:
        flags.append("deficit larger than 22% of TDEE")
    if profile.primary_goal == "lose_weight" and profile.age < 18 and result.calories < result.tdee - 1:
        flags.append("deficit applied to a minor")
    stated = _kcal_from_macros(result.protein_g, result.carbs_g, result.fat_g)
    if result.calories and abs(stated - result.calories) / result.calories > KCAL_TOLERANCE + 0.005:
        flags.append(f"macros add up to {round(stated)} kcal, not {result.calories}")
    if result.calories:
        fat_pct = result.fat_g * 9 / result.calories
        if not FAT_PCT_RANGE[0] <= fat_pct <= FAT_PCT_RANGE[1]:
            flags.append(f"fat is {round(fat_pct * 100)}% of calories")
        if result.protein_g * 4 / result.calories > 0.36:
            flags.append("protein above 35% of calories")
    if result.protein_g / profile.current_weight_kg > MAX_PROTEIN_G_PER_KG:
        flags.append(f"protein above {MAX_PROTEIN_G_PER_KG} g per kg of body weight")
    if result.carbs_g == 0:
        flags.append("carbohydrate target is 0 g")
    return flags


def build_sample_rows():
    rows = []
    n = 0
    for gender in GENDERS:
        for age in AGES:
            for build, kg, cm in BUILDS:
                for activity in ACTIVITIES:
                    for goal in GOALS:
                        n += 1
                        profile = SimpleNamespace(
                            gender=gender, age=age, current_weight_kg=kg, height_cm=cm,
                            activity_level=activity, primary_goal=goal,
                        )
                        r = gc.calculate_goals(profile)
                        cals = r.calories or 1
                        rows.append({
                            "scenario": n, "sex": gender, "age": age, "build": build, "weight_kg": kg,
                            "height_cm": cm, "activity": _label(activity), "goal": _label(goal),
                            "bmr": r.bmr, "tdee": r.tdee, "calories": r.calories, "protein_g": r.protein_g,
                            "carbs_g": r.carbs_g, "fat_g": r.fat_g, "kcal_vs_tdee": r.calories - r.tdee,
                            "protein_pct": round(r.protein_g * 4 / cals * 100), "carbs_pct": round(r.carbs_g * 4 / cals * 100),
                            "fat_pct": round(r.fat_g * 9 / cals * 100),
                            "protein_g_per_kg": round(r.protein_g / kg, 2),
                            "notes": " | ".join(r.assumptions), "flags": "; ".join(audit_goals(profile, r)),
                        })
    return rows


def build_food_rows():
    """Foods that cite no published table, most logged first."""
    used = dict(
        FoodItem.objects.filter(created_by__isnull=True).annotate(n=Count("foodentry")).values_list("id", "n")
    )
    rows = []
    for food in FoodItem.objects.filter(created_by__isnull=True).order_by("name"):
        if food.source_type != "estimated":
            continue
        implied = round(_kcal_from_macros(food.protein_g, food.carbs_g, food.fat_g))
        rows.append({
            "id": food.id, "name": food.name, "local_name": food.local_name, "category": food.category,
            "serving_description": food.serving_description, "serving_size_g": food.serving_size_g,
            "kcal": food.calories, "protein_g": food.protein_g, "carbs_g": food.carbs_g, "fat_g": food.fat_g,
            "kcal_from_macros": implied,
            "macros_vs_kcal": "ok" if macros_match_kcal(food.calories, food.protein_g, food.carbs_g, food.fat_g) else "DISAGREE",
            "source": food.source, "times_logged": used.get(food.id, 0),
            "reviewer_verdict (ok / change / remove)": "", "corrected_values_or_source": "", "reviewer_notes": "",
        })
    rows.sort(key=lambda r: (-r["times_logged"], r["name"]))
    return rows


def build_coach_md():
    from coach.services import llm_service
    lines = ["# Coach chat: safety rules as shipped", ""]
    lines.append("The coach is the one free-form use of the language model. These are its rules, read from the files in use.")
    lines += ["", "## System prompt", "", "```text"]
    try:
        lines.append(Path(llm_service.PROMPT_FILE).read_text(encoding="utf-8").strip())
    except OSError:
        lines.append("(prompt file not found)")
    lines.append("```")
    try:
        from coach.services import pain_guard
    except ImportError:
        pain_guard = None
    lines += ["", "## Pain and injury guard (rule in code)", ""]
    if pain_guard is None:
        lines.append("Not installed in this version.")
    else:
        lines.append("If a message mentions pain, stiffness, or a possible injury, the reply is forced into a short fixed form and the Detailed setting is ignored for that message.")
        lines += ["", "```text", pain_guard.PAIN_SYSTEM_BLOCK, "```"]
    return "\n".join(lines) + "\n"


def build_form_md(fingerprint):
    return f"""# Dietitian review form

Rules fingerprint: `{fingerprint}` (cite this when you sign; it changes whenever a rule changes)

Reviewer name: ____________________  Credentials / license no.: ____________________

Date: ____________________  Years of practice: ____________________

Mark each statement: Agree / Agree with changes / Disagree. Add notes where you do not fully agree.

| # | Statement | Verdict | Notes |
|---|---|---|---|
| 1 | Mifflin-St Jeor is an appropriate way to estimate energy needs for adult gym beginners (rules.md section 1). | | |
| 2 | The activity multipliers and the 0.95 beginner factor are appropriate. | | |
| 3 | The goal adjustments (+250 for muscle or weight gain, -500 for weight loss) are appropriate. | | |
| 4 | Limiting a weight-loss deficit to 20% of daily energy use is safe for beginners. | | |
| 5 | The calorie floors (1,500 male, 1,200 female, 1,350 other) are appropriate. | | |
| 6 | Not applying an automatic deficit to users under 18, with a note to see a doctor or dietitian, is appropriate. | | |
| 7 | The protein targets (1.2 to 1.4 g per kg, based on healthy-BMI weight, capped at 35% of calories) are appropriate. | | |
| 8 | The fat targets (20% to 30% of calories by goal), with carbohydrate filling the rest, are appropriate. | | |
| 9 | The sample goals in sample_goals.csv are balanced and safe (see the flags and notes columns). | | |
| 10 | Recalculating goals automatically when weight or profile changes, with an option to turn it off, is appropriate. | | |
| 11 | The calorie and macro values in foods_to_check.csv are acceptable, or my corrections are recorded in that file. | | |
| 12 | The food sources (PhilFCT, USDA, and listed estimates) are acceptable for a Filipino diet. | | |
| 13 | The chat coach's rules on diets, calories, medical conditions and eating disorders (coach_rules.md) are appropriate for gym beginners. | | |
| 14 | Goals are presented as general guidance and not medical advice; this is clear enough to users. | | |

Anything missing or unsafe that you would change: ______________________________________________

Signature: ____________________
"""


def _summary(fingerprint, sample_rows, food_rows, stats):
    flagged = [r for r in sample_rows if r["flags"]]
    lines = [
        "# Nutrition validation packet: summary", "",
        f"Generated {timezone.localdate().isoformat()}.", "",
        f"**Rules fingerprint: `{fingerprint}`** (changes whenever any rule or number in rules.md changes)", "",
        "## What to review", "",
        "1. `rules.md`: the formulas and numbers behind every calorie and macro goal (about 2 pages).",
        f"2. `sample_goals.csv`: {stats['scenarios']} calculated examples. Filter on the `flags` column first.",
        f"3. `foods_to_check.csv`: {len(food_rows)} foods that cite no published table. Fill in the verdict columns.",
        "4. `coach_rules.md`: the chat coach's rules.",
        "5. `review_form.md`: sign-off form.", "",
        "## Sample goal audit", "",
        f"- Examples built: {stats['scenarios']}",
        f"- Examples with at least one audit flag: {len(flagged)}",
    ]
    for r in flagged[:15]:
        lines.append(f"  - #{r['scenario']} ({r['sex']}, {r['age']}, {r['build']}, {r['activity']}, {r['goal']}): {r['flags']}")
    lines += ["", "## Food database (shared foods)", "", "| Source | Foods |", "|---|---|"]
    for key, count in stats["db_types"].items():
        lines.append(f"| {key} | {count} |")
    disagree = sum(1 for r in food_rows if r["macros_vs_kcal"] == "DISAGREE")
    lines += ["", f"Estimated foods whose calories and macros disagree by more than {round(MACRO_KCAL_TOLERANCE * 100)}%: {disagree}", "",
              "## Limits of this packet", "",
              "- Examples use fixed sample bodies, not real users.",
              "- Nutrient values are only as good as their source; foods added by users are private and excluded.",
              "- Nothing here is medical advice; the app presents goals as general guidance."]
    return "\n".join(lines) + "\n"


def build_packet():
    rules_body, fingerprint = build_rules_md()
    rules_md = f"{rules_body}\n\n---\n**Rules fingerprint: `{fingerprint}`**\n"
    sample_rows = build_sample_rows()
    food_rows = build_food_rows()
    db_types = {}
    for f in FoodItem.objects.filter(created_by__isnull=True):
        db_types[f.source_type] = db_types.get(f.source_type, 0) + 1
    stats = {
        "scenarios": len(sample_rows),
        "flagged": sum(1 for r in sample_rows if r["flags"]),
        "foods_to_check": len(food_rows),
        "db_types": dict(sorted(db_types.items())),
    }
    return Packet(rules_md, fingerprint, sample_rows, food_rows, build_coach_md(),
                  build_form_md(fingerprint), _summary(fingerprint, sample_rows, food_rows, stats), stats)


def write_packet(packet, out_dir):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for name, text in (("rules.md", packet.rules_md), ("coach_rules.md", packet.coach_md),
                       ("review_form.md", packet.form_md), ("summary.md", packet.summary_md)):
        (out / name).write_text(text, encoding="utf-8")
    # utf-8-sig so Excel opens Filipino names correctly
    for name, cols, rows in (("sample_goals.csv", SAMPLE_COLUMNS, packet.sample_rows),
                             ("foods_to_check.csv", FOOD_COLUMNS, packet.food_rows)):
        with open(out / name, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)
    return out
