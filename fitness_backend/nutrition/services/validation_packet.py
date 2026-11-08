"""
Review packet for expert (dietitian / adviser) validation of the meal suggestions.

Reviewers should sign off on RULES and DATA, not on individual outputs. This module
produces everything they need from the code itself, so the documents cannot drift from
what the app actually does:

  rules.md            every rule and number the suggester uses, read from the live
                      constants, with a fingerprint to cite ("validated rules a1b2c3d4e5f6")
  sample_plates.csv   plates built for a grid of calorie goals x meals, with an
                      independent sanity audit of each one (flags column)
  estimated_foods.csv foods that cite no published table (the ones to cross-check),
                      most-used-in-plates first, with empty verdict columns to fill in
  summary.md          counts, flags and the fingerprint, on one page

Nothing is written to the database: the sample plates are built for a throwaway user
inside a transaction that is always rolled back.
"""

import csv
import hashlib
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from nutrition.models import FoodItem, NutritionProfile
from nutrition.services import food_suggester as fs
from nutrition.services import meal_builder as mb
from nutrition.services import staples
from nutrition.services import suggestion_llm as llm

CALORIE_GOALS = (1500, 1800, 2200, 2600, 3000)
MEALS = ("breakfast", "lunch", "dinner", "snack")
PLATES_PER_SCENARIO = 3  # what the app shows by default
# Daily macro split used for the sample goals: 20% protein, 50% carbs, 30% fat.
SPLIT = {"protein": 0.20, "carbs": 0.50, "fat": 0.30}

# Audit thresholds. These are deliberately independent of the builder's own checks.
MACRO_KCAL_TOLERANCE = 0.40
MIN_KCAL_TO_CHECK = 50
# A plate smaller than this share of its meal's calorie target is not a meal.
MIN_PLATE_SHARE_OF_TARGET = mb.MIN_PLATE_FRACTION

SAMPLE_COLUMNS = [
    "scenario", "daily_kcal_goal", "meal", "option", "role", "food", "category", "source_type", "common_food",
    "amount", "grams", "kcal", "protein_g", "carbs_g", "fat_g", "plate_kcal", "plate_protein_g",
    "plate_carbs_g", "plate_fat_g", "flags",
]
ESTIMATED_COLUMNS = [
    "id", "name", "local_name", "category", "serving_description", "serving_size_g", "kcal",
    "protein_g", "carbs_g", "fat_g", "kcal_from_macros", "macros_vs_kcal", "source",
    "times_in_sample_plates", "reviewer_verdict (ok / change / remove)", "corrected_values_or_source",
    "reviewer_notes",
]


RAW_COLUMNS = [
    "id", "name", "category", "source", "kcal", "protein_g", "carbs_g", "fat_g", "named_like_a_common_food",
    "reviewer_verdict (really raw / actually cooked)",
]


class _Rollback(Exception):
    pass


@dataclass
class Packet:
    rules_md: str
    fingerprint: str
    sample_rows: list
    estimated_rows: list
    summary_md: str
    raw_rows: list = field(default_factory=list)
    stats: dict = field(default_factory=dict)


# --------------------------------------------------------------------------- rules


def _role_lines():
    seen = {}
    for meal, roles in mb.MEAL_ROLES.items():
        for role in roles:
            seen.setdefault(role.name, {})[meal] = role
    lines = []
    for meal, roles in mb.MEAL_ROLES.items():
        lines.append(f"**{meal.title()}** (about {round(fs.MEAL_CALORIE_SHARE[meal] * 100)}% of the daily calorie goal)")
        lines.append("")
        lines.append("| Plate part | Allowed food groups | Portion on the plate | Other conditions |")
        lines.append("|---|---|---|---|")
        for role in roles:
            conditions = []
            if role.min_protein_100:
                conditions.append(f"at least {role.min_protein_100:g} g protein per 100 g")
            if role.min_carbs_100:
                conditions.append(f"at least {role.min_carbs_100:g} g carbs per 100 g")
            if role.max_fat_100 < 10_000:
                conditions.append(f"at most {role.max_fat_100:g} g fat per 100 g")
            if role.max_kcal_100 < 10_000:
                conditions.append(f"at most {role.max_kcal_100:g} kcal per 100 g")
            if role.prefer:
                conditions.append(f"ranked first when the name contains: {', '.join(role.prefer)}")
            if role.no_canned_in:
                conditions.append("canned items not offered in: " + ", ".join(str(c.label) for c in role.no_canned_in))
            if role.balance_groups:
                conditions.append(
                    f"food groups are mixed: shortlist takes turns across groups, and at most plates//"
                    f"{mb.PLATES_PER_MAIN_GROUP_DIVISOR} plates (at least 1) share a main-item group"
                )
            if role.rotate:
                conditions.append(
                    "these groups share one plate slot, and the date decides which goes first (lunch and dinner alternate): "
                    + ", ".join(str(c.label) for c in role.rotate)
                )
            if role.families:
                conditions.append(
                    "shortlist takes one food from each of these families in turn: "
                    + "; ".join("(" + ", ".join(words) + ")" for words in role.families)
                )
            if not role.required:
                conditions.append("optional")
            groups = ", ".join(str(c.label) for c in role.categories)
            lines.append(f"| {role.name} | {groups} | {role.min_g}-{role.max_g} g | {'; '.join(conditions) or '-'} |")
        lines.append("")
    return lines


def build_rules_md():
    """Returns (markdown, fingerprint). The fingerprint covers the rules only, not the date."""
    body = []
    add = body.append

    add("## 1. What the app is allowed to do")
    add("")
    add("- Every food, portion and nutrient number comes from the food database. The AI model never produces numbers.")
    add("- Rules choose the candidate foods and portions. The AI model may only **pick among candidates by id** and write a")
    add(f"  one-sentence reason (at most {llm.MAX_REASON_CHARS} characters). Picks that are not in the list are discarded;")
    add(f"  fewer than {llm.MIN_VALID_PICKS} valid picks means the app falls back to rule-based reasons.")
    add("- Suggestions are general guidance for healthy gym beginners, not medical or clinical advice.")
    add("")

    add("## 2. When nothing is suggested")
    add("")
    add(f"- Single foods: less than {fs.MIN_REMAINING_CALORIES} kcal left in the day.")
    add(f"- Full plates: less than {mb.MIN_PLATE_CALORIES} kcal left in the day.")
    add(f"- A plate must reach at least {round(mb.MIN_PLATE_FRACTION * 100)}% of the meal's calorie target.")
    add("- A plate never exceeds the calories left in the day.")
    add("")

    add("## 3. Meal targets")
    add("")
    add("Meal target = the meal's share of the daily goal (below), but never more than what is left today.")
    add("Protein, carbs and fat are targeted in proportion to what is left of each for the day.")
    add("")
    add("| Meal | Share of daily calories |")
    add("|---|---|")
    for meal, share in fs.MEAL_CALORIE_SHARE.items():
        add(f"| {meal.title()} | {round(share * 100)}% |")
    add("")

    add("## 4. Plate structure")
    add("")
    body.extend(_role_lines())
    add(f"**Larger meals.** The portion ranges above fit a meal of about {mb.REFERENCE_MEAL_CALORIES} kcal. For a bigger meal "
        f"target, the upper limit of the {', '.join(mb.SCALED_ROLES)} parts grows in proportion (meal target / "
        f"{mb.REFERENCE_MEAL_CALORIES}), up to {mb.MAX_PORTION_SCALE:g} times, so a high-calorie day can be reached. Smaller meals "
        "use the ranges as written.")
    add("")
    bulky = {}
    for meal, roles in mb.MEAL_ROLES.items():
        for role in roles:
            if role.low_density_factor != 1.0:
                bulky.setdefault(id(role), (role, []))[1].append(meal)
    for role, meals in bulky.values():
        add(f"**Bulky {role.name} at {' and '.join(meals)}.** A {role.name} with fewer than {mb.LOW_DENSITY_KCAL_100} kcal per "
            f"100 g and fewer than {mb.LOW_DENSITY_MAX_PROTEIN_100} g protein per 100 g (watery foods such as cooked oatmeal, lugaw or tofu; "
            f"not lean meat or canned tuna) may be served up to {role.low_density_factor:g} times the upper limit, "
            "because a full portion of it is very low in calories.")
        add("")
    add(f"**Preferred foods.** A plate made of a role's preferred foods earns up to {mb.W_PREFERRED} extra plate score (section 8).")
    add("")

    add("## 5. Largest portion of a single-food suggestion")
    add("")
    add("These caps apply to the single-food suggestions (\"Single foods\" mode). Parts of a full plate follow the")
    add("portion ranges in section 4 instead (for example a plate may hold up to 250 g of rice or root crops, more for a large meal).")
    add("")
    add("| Food group | Max grams |")
    add("|---|---|")
    for cat, grams in fs.MAX_PORTION_G.items():
        add(f"| {cat.label} | {grams} g |")
    add(f"| any other group | {fs.DEFAULT_MAX_PORTION_G} g |")
    add("")
    add(f"Portions move in steps of {fs.SERVING_STEP:g} serving, from {fs.MIN_SERVINGS:g} to {fs.MAX_SERVINGS_SUGGESTED:g} servings.")
    add("")

    add("## 6. Foods that are never suggested")
    add("")
    add(f"- Not ready to eat (always excluded): `{fs._NOT_READY_ALWAYS.pattern}`")
    add(f"- Raw foods are excluded except in: {', '.join(sorted(str(c.label) for c in fs._RAW_OK_CATEGORIES))}.")
    add(f"- Not a side dish (vegetable/fruit groups only): `{mb._NOT_A_SIDE.pattern}`")
    add(f"- Flavourings, not a vegetable portion: `{mb._AROMATIC.pattern}`")
    add(f"- Unripe fruit is not offered as a fruit side (`{mb._UNRIPE.pattern}`). Dry cereal is not offered as a carb "
        f"(`{mb._DRY.pattern}`); its cooked or prepared row is.")
    add(f"- Desserts, fried snacks and factory patties are never a plate part (names containing: "
        f"{', '.join(staples.NOT_A_MEAL_PART_WORDS)}).")
    add("- Ingredients, not a portion of food (never suggested): " + "; ".join(
        f"{c.label}: `{p.pattern}`" for c, p in staples.INGREDIENT_ONLY.items()))
    add(f"- Never suggested to a beginner (balut and other embryo eggs, ant eggs, eggnog): `{staples.ODD_FOODS.pattern}`")
    groups = ", ".join(str(c.label) for c in staples.MUST_BE_PREPARED)
    add(f"- Treated as raw and not suggested: foods in these groups whose name does not say how they were prepared ({groups}).")
    add("  PhilFCT lists raw foods under a plain name (\"Tilapia\", \"Chicken white meat\", \"Potato\"), and raw chicken or pork is unsafe.")
    add(f"  Accepted preparation words: {', '.join(staples.PREPARED_WORDS)}.")
    add("  Foods a user added themselves, and Open Food Facts products (packaged retail items), are not judged this way.")
    add("- A plate's carb must be at most the calories per 100 g shown in section 4, which keeps out dry rice, flour and dry pasta.")
    add("")

    add("## 7. Variety")
    add("")
    add(f"- No more than {fs.MAX_PER_CATEGORY} single-food suggestions from one food group.")
    add(f"- No more than {mb.MAX_PLATES_PER_SIDE} plates share the same carb or vegetable.")
    add("- A food already logged today is not the main item of a plate again; \"show different ideas\" skips foods already shown.")
    add("")

    add("## 8. Ranking weights (0 to 1 each, higher is better)")
    add("")
    add("| Single food | Weight | | Plate | Weight |")
    add("|---|---|---|---|---|")
    single = [
        ("Fills remaining protein", fs.W_PROTEIN_FIT), ("Lean protein per calorie", fs.W_PROTEIN_DENSITY),
        ("Calories near meal target", fs.W_CALORIE_FIT), ("User already eats it", fs.W_FAMILIAR),
        ("Within remaining carbs/fat", fs.W_CARB_FAT_FIT), ("Filipino-sourced data (PhilFCT) bonus", fs.PHILFCT_BONUS),
    ]
    plate = [
        ("Fit to calorie and macro targets", mb.W_FIT), ("User already eats the foods", mb.W_FAMILIAR),
        ("Has a vegetable or fruit", mb.W_COMPLETE), ("Filipino-sourced data", mb.W_FILIPINO),
        ("Made of the role's preferred foods (breakfast)", mb.W_PREFERRED),
    ]
    for i in range(max(len(single), len(plate))):
        a = single[i] if i < len(single) else ("", "")
        b = plate[i] if i < len(plate) else ("", "")
        add(f"| {a[0]} | {a[1]} | | {b[0]} | {b[1]} |")
    add("")

    add("## 9. Common foods are ranked first")
    add("")
    add("The food database is mostly ingredient-level and includes rare items (abalone, ant eggs, obscure leaf")
    add("vegetables). Ranking by nutrients alone favours whatever has the most protein per calorie, so suggestions")
    add("also prefer foods on this list. A food matching a keyword in its group gets a ranking boost; it is not a")
    add("filter, so other foods can still appear when a group has few matches. Edit the lists in")
    add("`nutrition/services/staples.py`.")
    add("")
    add("| Group | Counts as a common food when the name contains |")
    add("|---|---|")
    labels = {"protein": "Protein foods (meat, fish, eggs, legumes)", "dairy": "Dairy", "carb": "Rice, grains, roots",
              "veg": "Vegetables", "fruit": "Fruits"}
    for kind, words in staples.STAPLES.items():
        add(f"| {labels[kind]} | {', '.join(words)} |")
    add("")
    add("Soups and snacks have no list and are not judged.")
    add("")
    add("Not counted as common even when the name matches a keyword above (look-alikes):")
    add("")
    add("| Group | Names containing |")
    add("|---|---|")
    for kind, words in staples.NOT_COMMON.items():
        add(f"| {labels[kind]} | {'; '.join(words)} |")  # ";" because one entry is "radish, pod"
    add("")
    add(f"- Ranked lower (high sodium), never banned: names containing {', '.join(staples.LESS_PREFERRED_WORDS)}.")
    add("- Ranked lower and never boosted, never banned (protein groups only; judgment calls for the reviewer):")
    add(f"  - factory and deli meats: {', '.join(staples.PROCESSED_MEAT_WORDS)}")
    add(f"  - organ meats: {', '.join(staples.ORGAN_MEAT_WORDS)} (\"kidney beans\" are not affected)")
    add(f"- Boost for a role's preferred foods (breakfast, section 4): {mb.W_PREFER} when choosing a plate part's shortlist.")
    add(f"- Boost for a common food: {staples.W_STAPLE_POOL} when choosing a plate part's shortlist, "
        f"{staples.W_STAPLE_SCORE} in the single-food score. Penalty for dried/salted, deli/factory and organ meats: {staples.PENALTY_POOL} / {staples.PENALTY_SCORE}.")
    add("- Among equally ranked foods the order rotates from day to day instead of following the alphabet.")
    add("")

    body_text = "\n".join(body)
    fingerprint = hashlib.sha256(body_text.encode()).hexdigest()[:12]
    return body_text, fingerprint


# --------------------------------------------------------------------------- audit


def _kcal_from_macros(protein, carbs, fat):
    return protein * 4 + carbs * 4 + fat * 9


def macros_match_kcal(kcal, protein, carbs, fat):
    """False when the stated calories and the macros disagree by more than the tolerance."""
    if kcal < MIN_KCAL_TO_CHECK:
        return True
    return abs(_kcal_from_macros(protein, carbs, fat) - kcal) / kcal <= MACRO_KCAL_TOLERANCE


def plate_part_limits():
    """{(meal, plate part): largest grams}. Plates use their own portion ranges (rules.md section 4)."""
    return {(meal, role.name): role.max_g for meal, roles in mb.MEAL_ROLES.items() for role in roles}


def effective_cap(cap, item, meal_target_kcal, meal=None):
    """The plate limit that applies to this item: the base range, widened for a large meal and for bulky carbs (rules.md section 4)."""
    if item["role"] in mb.SCALED_ROLES:
        cap = cap * mb.portion_scale_for(meal_target_kcal)
    role = next((r for r in mb.MEAL_ROLES.get(meal, ()) if r.name == item["role"]), None)
    if role and item["grams"] and mb.is_low_density(item["kcal"] * 100 / item["grams"], item["protein_g"] * 100 / item["grams"]):
        cap = cap * role.low_density_factor
    return cap


def audit_plate(items, plate_kcal, remaining_kcal, meal_target_kcal, meal, limits=None):
    """
    Independent sanity checks on one finished plate. `items` are dicts with role, grams,
    kcal, protein_g, carbs_g, fat_g, food. Returns a list of flag strings (empty = nothing to review).
    """
    limits = limits if limits is not None else plate_part_limits()
    flags = []
    if plate_kcal < meal_target_kcal * MIN_PLATE_SHARE_OF_TARGET:
        flags.append(
            f"plate is under {round(MIN_PLATE_SHARE_OF_TARGET * 100)}% of the meal target ({round(meal_target_kcal)} kcal)"
        )
    if plate_kcal > remaining_kcal + 1:
        flags.append("plate over the calories left today")
    for item in items:
        cap = limits.get((meal, item["role"]))
        if cap is not None:
            cap = effective_cap(cap, item, meal_target_kcal, meal)
        if cap is not None and item["grams"] > cap + 0.5:
            flags.append(f"{item['food']}: {item['grams']:g} g is over the {cap:g} g plate limit")
        if not macros_match_kcal(item["kcal"], item["protein_g"], item["carbs_g"], item["fat_g"]):
            flags.append(f"{item['food']}: calories and macros disagree")
        if item.get("common") is False:
            flags.append(f"{item['food']}: not on the common-foods list")
    return flags


# --------------------------------------------------------------------------- sample plates


def _scenario_goals(kcal):
    return {
        "daily_calories_goal": kcal,
        "daily_protein_goal": round(kcal * SPLIT["protein"] / 4),
        "daily_carbs_goal": round(kcal * SPLIT["carbs"] / 4),
        "daily_fat_goal": round(kcal * SPLIT["fat"] / 9),
    }


def build_sample_rows(goals=CALORIE_GOALS, meals=MEALS, per_scenario=PLATES_PER_SCENARIO):
    """Builds plates for every goal x meal as plain rows. Always rolls back; nothing is saved."""
    rows = []
    today = timezone.localdate()
    limits = plate_part_limits()
    User = get_user_model()
    try:
        with transaction.atomic():
            user = User.objects.create_user(email="validation-packet@example.invalid", password="not-used")
            for kcal in goals:
                profile, _ = NutritionProfile.objects.update_or_create(user=user, defaults=_scenario_goals(kcal))
                for meal in meals:
                    remaining, plates = mb.build_meal_suggestions(user, profile, meal, today, limit=per_scenario)
                    scenario = f"{kcal} kcal / {meal}"
                    if not plates:
                        rows.append({"scenario": scenario, "daily_kcal_goal": kcal, "meal": meal, "option": 0,
                                     "flags": "no plate could be built"})
                        continue
                    for index, plate in enumerate(plates[:per_scenario], start=1):
                        items = []
                        for it in plate.items:
                            food = it.food
                            items.append({
                                "role": it.role, "food": food.name, "category": food.category,
                                "source_type": food.source_type, "amount": it.amount_label,
                                "common": staples.is_staple(food), "common_food": "yes" if staples.is_staple(food) else "no",
                                "grams": round(it.servings * food.serving_size_g, 1),
                                "kcal": round(it.calories), "protein_g": round(it.protein_g, 1),
                                "carbs_g": round(it.carbs_g, 1), "fat_g": round(it.fat_g, 1),
                                "food_id": food.id,
                            })
                        meal_target = min(remaining.calories, remaining.goal_calories * fs.MEAL_CALORIE_SHARE[meal])
                        flags = audit_plate(items, plate.calories, remaining.calories, meal_target, meal, limits)
                        for item in items:
                            rows.append({
                                "scenario": scenario, "daily_kcal_goal": kcal, "meal": meal, "option": index,
                                **{k: item[k] for k in ("role", "food", "category", "source_type", "common_food", "amount", "grams",
                                                        "kcal", "protein_g", "carbs_g", "fat_g", "food_id")},
                                "plate_kcal": round(plate.calories), "plate_protein_g": round(plate.protein_g, 1),
                                "plate_carbs_g": round(plate.carbs_g, 1), "plate_fat_g": round(plate.fat_g, 1),
                                "flags": "; ".join(flags),
                            })
            raise _Rollback
    except _Rollback:
        pass
    return rows


# --------------------------------------------------------------------------- estimated foods


def build_estimated_rows(used_counts):
    """Foods that cite no published table, most used in the sample plates first."""
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
            "macros_vs_kcal": "ok" if macros_match_kcal(food.calories, food.protein_g, food.carbs_g, food.fat_g)
            else "DISAGREE",
            "source": food.source, "times_in_sample_plates": used_counts.get(food.id, 0),
            "reviewer_verdict (ok / change / remove)": "", "corrected_values_or_source": "", "reviewer_notes": "",
        })
    rows.sort(key=lambda r: (-r["times_in_sample_plates"], r["name"]))
    return rows


def build_raw_rows():
    """
    Shared foods left out of suggestions because their name does not say how they were prepared.
    Listed so a reviewer can spot a cooked food that was dropped by mistake. Common-looking names first.
    Foods whose name literally says raw / uncooked are not listed (they are right to leave out; see
    count_labelled_raw).
    """
    rows = []
    for food in FoodItem.objects.filter(created_by__isnull=True).order_by("name"):
        if not staples.looks_raw(food) or staples.is_labelled_raw(food):
            continue
        rows.append({
            "id": food.id, "name": food.name, "category": food.category, "source": food.source,
            "kcal": food.calories, "protein_g": food.protein_g, "carbs_g": food.carbs_g, "fat_g": food.fat_g,
            "named_like_a_common_food": "yes" if staples.is_staple(food) else "no",
            "reviewer_verdict (really raw / actually cooked)": "",
        })
    rows.sort(key=lambda r: (r["named_like_a_common_food"] != "yes", r["name"]))
    return rows


def count_labelled_raw():
    """Shared foods left out whose name says raw / uncooked: nothing to review, just reported."""
    return sum(
        1 for food in FoodItem.objects.filter(created_by__isnull=True)
        if staples.looks_raw(food) and staples.is_labelled_raw(food)
    )


# --------------------------------------------------------------------------- assemble


def _summary(fingerprint, sample_rows, estimated_rows, used_by_type, raw_rows=(), labelled_raw=0):
    plates = {(r["scenario"], r["option"]) for r in sample_rows if r["option"]}
    empty = [r["scenario"] for r in sample_rows if not r["option"]]
    flagged = {(r["scenario"], r["option"]): r["flags"] for r in sample_rows if r.get("flags") and r["option"]}
    db_types = Counter(f.source_type for f in FoodItem.objects.filter(created_by__isnull=True))
    in_plates = sum(1 for r in estimated_rows if r["times_in_sample_plates"])
    parts = [r for r in sample_rows if r.get("food_id")]
    uncommon = sum(1 for r in parts if r["common_food"] == "no")
    disagree = sum(1 for r in estimated_rows if r["macros_vs_kcal"] == "DISAGREE")

    lines = [
        "# Meal suggestion validation packet", "",
        f"Generated: {timezone.localdate().isoformat()}  ",
        f"**Rules fingerprint: `{fingerprint}`** (changes whenever any rule or number in rules.md changes)", "",
        "## What to review", "",
        "1. `rules.md`: the rules and numbers behind every suggestion (about 2 pages).",
        f"2. `estimated_foods.csv`: {len(estimated_rows)} foods that cite no published table. "
        + (f"{in_plates} of them appear in the sample plates; start there. Fill in the verdict columns."
           if in_plates else "None appear in the sample plates." if estimated_rows else "None; every food cites a published table."),
        f"3. `sample_plates.csv`: {len(plates)} sample plates across {len(CALORIE_GOALS)} calorie goals and "
        f"{len(MEALS)} meals. Spot-check, filtering on the `flags` column first.",
        "4. `raw_looking_foods.csv`: foods left out because they look raw. Check that nothing cooked is on it.", "",
        "## Database composition (shared foods only)", "",
        "| Source | Foods |", "|---|---|",
    ]
    for key in ("philfct", "usda", "openfoodfacts", "estimated"):
        lines.append(f"| {key} | {db_types.get(key, 0)} |")
    lines += ["", "## Sample plate audit", "",
              f"- Plates built: {len(plates)}",
              f"- Plates with at least one audit flag: {len(flagged)}"]
    for key, text in list(flagged.items())[:15]:
        lines.append(f"  - {key[0]}, option {key[1]}: {text}")
    if empty:
        lines.append(f"- Scenarios where no plate could be built ({len(empty)}): " + ", ".join(empty[:10]))
    lines.append(f"- Plate parts on the common-foods list: {len(parts) - uncommon} of {len(parts)} "
                 f"(see rules.md section 9)")
    lines.append("- Plate parts by source: " + ", ".join(f"{k} {v}" for k, v in sorted(used_by_type.items())))
    raw_common = sum(1 for r in raw_rows if r["named_like_a_common_food"] == "yes")
    lines.append(
        f"- Foods left out because the name does not say how they were prepared (treated as raw): {len(raw_rows)}, "
        f"of which {raw_common} have common names. Scan `raw_looking_foods.csv` and mark any that are actually cooked."
    )
    lines.append(
        f"- Foods left out because the name itself says raw or uncooked: {labelled_raw} (correct, not listed)."
    )
    lines += ["", f"Estimated foods whose calories and macros disagree by more than {round(MACRO_KCAL_TOLERANCE * 100)}%: {disagree}", "",
              "## Limits of this packet", "",
              "- Sample plates use a fixed 20/50/30 protein/carb/fat split and a full day remaining; real users differ.",
              "- Nutrient values are only as good as their source; foods from user-added entries are private and excluded.",
              "- Nothing here is medical advice; the app presents suggestions as general guidance."]
    return "\n".join(lines) + "\n"


def build_packet(goals=CALORIE_GOALS, meals=MEALS):
    rules_body, fingerprint = build_rules_md()
    sample_rows = build_sample_rows(goals=goals, meals=meals)

    plate_parts = [r for r in sample_rows if r.get("food_id")]
    used_counts = Counter(r["food_id"] for r in plate_parts)
    used_by_type = Counter(r["source_type"] for r in plate_parts)
    estimated_rows = build_estimated_rows(used_counts)
    raw_rows = build_raw_rows()
    labelled_raw = count_labelled_raw()

    rules_md = (
        "# Meal suggestion rules\n\n"
        f"**Rules fingerprint: `{fingerprint}`**  \n"
        "Generated from the live code, so this file is exactly what the app does.\n\n" + rules_body + "\n"
    )
    summary = _summary(fingerprint, sample_rows, estimated_rows, used_by_type, raw_rows, labelled_raw)
    return Packet(rules_md, fingerprint, sample_rows, estimated_rows, summary, raw_rows,
                  stats={"plates": len({(r["scenario"], r["option"]) for r in sample_rows if r["option"]}),
                         "estimated_foods": len(estimated_rows), "raw_looking_foods": len(raw_rows),
                         "labelled_raw_foods": labelled_raw})


def write_packet(packet, out_dir):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "rules.md").write_text(packet.rules_md, encoding="utf-8")
    (out / "summary.md").write_text(packet.summary_md, encoding="utf-8")
    # utf-8-sig so Excel opens the Filipino names correctly
    with open(out / "sample_plates.csv", "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=SAMPLE_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(packet.sample_rows)
    with open(out / "estimated_foods.csv", "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=ESTIMATED_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(packet.estimated_rows)
    with open(out / "raw_looking_foods.csv", "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=RAW_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(packet.raw_rows)
    return out
