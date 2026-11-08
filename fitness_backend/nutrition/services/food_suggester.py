"""
Meal-suggestion engine for Fita: what could the user eat NEXT, given what
they have left today?

Design (same hybrid idea as the progress reports):

  1. RULES decide the candidates. Everything here is deterministic and
     grounded in FoodItem rows: how much of the day's calories/macros are
     left, which food categories suit the meal, a sensible portion, and a
     score for how well each food fills the gap.
  2. The LLM (see suggestion_llm.py) may only RE-RANK and EXPLAIN those
     candidates by id. It can't invent a food or change a number, so every
     suggestion is a real database item the user can log in one tap.

If the LLM is unavailable (no key, rate limit, bad JSON) the rule-based
top picks are returned with templated reasons -- the feature degrades, it
doesn't break.
"""

import math
import re
from dataclasses import dataclass, field

from django.db.models import Count, Q, Sum
from django.utils import timezone

from nutrition.models import FoodCategory, FoodEntry, FoodItem
from nutrition.services import staples

# Categories that make sense per meal. Data is per-ingredient/per-100g, so
# these are broad on purpose; the scoring does the real narrowing.
MEAL_CATEGORIES = {
    "breakfast": [
        FoodCategory.RICE_GRAINS,
        FoodCategory.EGGS,
        FoodCategory.DAIRY,
        FoodCategory.FRUITS,
        FoodCategory.ROOTS_TUBERS,
        FoodCategory.NUTS_LEGUMES,
        FoodCategory.VIANDS_MEAT,
        FoodCategory.VIANDS_FISH,
    ],
    "lunch": [
        FoodCategory.VIANDS_MEAT,
        FoodCategory.VIANDS_FISH,
        FoodCategory.EGGS,
        FoodCategory.NUTS_LEGUMES,
        FoodCategory.VEGETABLES,
        FoodCategory.RICE_GRAINS,
        FoodCategory.ROOTS_TUBERS,
        FoodCategory.SOUPS,
    ],
    "dinner": [
        FoodCategory.VIANDS_MEAT,
        FoodCategory.VIANDS_FISH,
        FoodCategory.EGGS,
        FoodCategory.NUTS_LEGUMES,
        FoodCategory.VEGETABLES,
        FoodCategory.RICE_GRAINS,
        FoodCategory.ROOTS_TUBERS,
        FoodCategory.SOUPS,
    ],
    "snack": [
        FoodCategory.FRUITS,
        FoodCategory.NUTS_LEGUMES,
        FoodCategory.DAIRY,
        FoodCategory.SNACKS,
        FoodCategory.ROOTS_TUBERS,
        FoodCategory.EGGS,
    ],
}

# Rough share of the daily calorie goal each meal should cover.
MEAL_CALORIE_SHARE = {"breakfast": 0.25, "lunch": 0.35, "dinner": 0.30, "snack": 0.10}

# Not worth suggesting once the day is basically full.
MIN_REMAINING_CALORIES = 80

# Cooked/ready foods only: "Pork belly, raw" or "Rice flour" aren't meals.
# Raw is fine for fruit and vegetables.
_NOT_READY_ALWAYS = re.compile(r"\b(uncooked|unprepared|powder|pwdr|flour|dehydrated|concentrate)\b", re.I)
_RAW = re.compile(r"\braw\b", re.I)
_RAW_OK_CATEGORIES = {FoodCategory.FRUITS, FoodCategory.VEGETABLES}

MAX_PER_CATEGORY = 3  # variety: no ten-egg suggestion lists
SERVING_STEP = 0.5
MIN_SERVINGS = 0.5
MAX_SERVINGS_SUGGESTED = 4.0

# Largest portion worth suggesting, in grams of food, per category. Without
# this a lean, low-calorie food gets scaled up to the calorie target (350 g
# of tilapia, 90 g of protein in one go). A suggestion should look like
# something you'd actually put on a plate.
MAX_PORTION_G = {
    FoodCategory.VIANDS_MEAT: 150,
    FoodCategory.VIANDS_FISH: 150,
    FoodCategory.EGGS: 150,
    FoodCategory.NUTS_LEGUMES: 150,
    FoodCategory.RICE_GRAINS: 200,
    FoodCategory.ROOTS_TUBERS: 200,
    FoodCategory.VEGETABLES: 200,
    FoodCategory.FRUITS: 200,
    FoodCategory.DAIRY: 250,
    FoodCategory.SOUPS: 350,
    FoodCategory.SNACKS: 100,
}
DEFAULT_MAX_PORTION_G = 200

# Score weights (each component is 0..1). Tweak here, not in the maths.
W_PROTEIN_FIT = 0.35  # fills the remaining protein
W_PROTEIN_DENSITY = 0.20  # lean protein per calorie
W_CALORIE_FIT = 0.20  # portion lands near the meal's calorie target
W_FAMILIAR = 0.15  # the user already eats this
W_CARB_FAT_FIT = 0.10  # doesn't blow past remaining carbs/fat
PHILFCT_BONUS = 0.05  # Filipino-sourced data first


@dataclass
class Remaining:
    goal_calories: float
    calories: float
    protein_g: float
    carbs_g: float
    fat_g: float


@dataclass
class Suggestion:
    food: FoodItem
    servings: float
    calories: float
    protein_g: float
    carbs_g: float
    fat_g: float
    amount_label: str
    score: float
    reason: str = ""
    reason_source: str = "rule"
    flags: list = field(default_factory=list)


def compute_remaining(nutrition_profile, date):
    """Goals minus what's logged on `date` (never below zero)."""
    totals = FoodEntry.objects.filter(
        daily_entry__nutrition_profile=nutrition_profile, daily_entry__date=date
    ).aggregate(
        calories=Sum("calories"),
        protein_g=Sum("protein_g"),
        carbs_g=Sum("carbs_g"),
        fat_g=Sum("fat_g"),
    )

    def left(goal, eaten):
        return max(goal - (eaten or 0), 0.0)

    return Remaining(
        goal_calories=nutrition_profile.daily_calories_goal,
        calories=left(nutrition_profile.daily_calories_goal, totals["calories"]),
        protein_g=left(nutrition_profile.daily_protein_goal, totals["protein_g"]),
        carbs_g=left(nutrition_profile.daily_carbs_goal, totals["carbs_g"]),
        fat_g=left(nutrition_profile.daily_fat_goal, totals["fat_g"]),
    )


def recent_food_counts(nutrition_profile, date, days=30):
    """{food_id: times logged in the last `days` days}, so suggestions favour what the user really eats."""
    since = date - timezone.timedelta(days=days)
    return dict(
        FoodEntry.objects.filter(
            daily_entry__nutrition_profile=nutrition_profile,
            daily_entry__date__gte=since,
            daily_entry__date__lte=date,
        )
        .values_list("food_item_id")
        .annotate(n=Count("id"))
    )


def foods_logged_on(nutrition_profile, date):
    """Ids of foods already logged on `date`."""
    return set(
        FoodEntry.objects.filter(
            daily_entry__nutrition_profile=nutrition_profile, daily_entry__date=date
        ).values_list("food_item_id", flat=True)
    )


def _is_ready_to_eat(food):
    if _NOT_READY_ALWAYS.search(food.name) or staples.looks_raw(food) or staples.is_ingredient_only(food):
        return False
    if _RAW.search(food.name) and food.category not in _RAW_OK_CATEGORIES:
        return False
    return True


def _round_to_step(value, step=SERVING_STEP):
    return round(value / step) * step


def _suggested_servings(food, ideal_item_cal):
    """Servings that reach the calorie target, kept to a realistic portion."""
    servings = _round_to_step(ideal_item_cal / food.calories)

    max_grams = MAX_PORTION_G.get(food.category, DEFAULT_MAX_PORTION_G)
    max_servings = math.floor(max_grams / max(food.serving_size_g, 1) / SERVING_STEP) * SERVING_STEP
    servings = min(servings, max_servings)

    return min(max(servings, MIN_SERVINGS), MAX_SERVINGS_SUGGESTED)


def _amount_label(food, servings):
    """'150 g' for per-100g imports; '1 cup cooked' / '2 x 1 piece (medium)' otherwise."""
    if food.serving_description.strip().lower() in {"100g", "100 g"}:
        return f"{round(servings * food.serving_size_g):g} g"
    if servings == 1:
        return food.serving_description
    return f"{servings:g} x {food.serving_description}"


def _score(food, servings, remaining, ideal_item_cal, familiar_count):
    item_cal = food.calories * servings
    item_protein = food.protein_g * servings
    item_carbs = food.carbs_g * servings
    item_fat = food.fat_g * servings

    # Protein fit only matters while there's protein left to eat.
    if remaining.protein_g > 5:
        protein_fit = min(item_protein / remaining.protein_g, 1.0)
    else:
        protein_fit = 0.5
    protein_density = min(((food.protein_g * 4) / food.calories) / 0.40, 1.0) if food.calories else 0.0
    calorie_fit = max(1 - abs(item_cal - ideal_item_cal) / ideal_item_cal, 0.0)
    familiar = min(familiar_count, 5) / 5

    over_carbs = max(item_carbs - remaining.carbs_g, 0) / max(remaining.carbs_g, 30)
    over_fat = max(item_fat - remaining.fat_g, 0) / max(remaining.fat_g, 15)
    carb_fat_fit = max(1 - (over_carbs + over_fat) / 2, 0.0)

    score = (
        W_PROTEIN_FIT * protein_fit
        + W_PROTEIN_DENSITY * protein_density
        + W_CALORIE_FIT * calorie_fit
        + W_FAMILIAR * familiar
        + W_CARB_FAT_FIT * carb_fat_fit
    )
    if food.source.startswith("PhilFCT"):
        score += PHILFCT_BONUS
    # Nutrients alone favour whatever has the most protein per calorie (dried anchovy, abalone):
    # lean towards foods people actually eat, and away from high-sodium dried/salted ones.
    if staples.is_staple(food):
        score += staples.W_STAPLE_SCORE
    if staples.less_preferred(food):
        score -= staples.PENALTY_SCORE
    return round(score, 4)


def _templated_reason(suggestion, remaining):
    """Plain, numbers-only explanation used when the LLM isn't available."""
    kcal = f"about {suggestion.calories:.0f} kcal"
    if remaining.protein_g > 5 and suggestion.protein_g >= 0.2 * remaining.protein_g:
        return (
            f"{suggestion.protein_g:.0f} g protein toward the "
            f"{remaining.protein_g:.0f} g you have left, for {kcal}."
        )
    if suggestion.protein_g * 4 >= 0.25 * max(suggestion.calories, 1):
        return f"Good protein for its calories ({suggestion.protein_g:.0f} g in {kcal})."
    return f"Fits your remaining calories at {kcal}."


def build_suggestions(user, nutrition_profile, meal_type, date, limit=8, exclude_ids=()):
    """
    Returns (remaining, suggestions). `suggestions` is the rule-based top
    `limit` (already sorted best-first); empty if the day is basically full.
    `exclude_ids` are foods the user has already been shown (for a "show
    different ideas" request) and are never returned.
    """
    remaining = compute_remaining(nutrition_profile, date)
    if remaining.calories < MIN_REMAINING_CALORIES:
        return remaining, []

    meal_target = min(remaining.calories, remaining.goal_calories * MEAL_CALORIE_SHARE[meal_type])
    ideal_item_cal = min(max(meal_target * 0.4, 80), 450)

    categories = MEAL_CATEGORIES[meal_type]
    candidates = FoodItem.objects.filter(category__in=categories, calories__gte=40).filter(
        Q(created_by__isnull=True) | Q(created_by=user)
    )

    already_today = foods_logged_on(nutrition_profile, date) | set(exclude_ids)
    familiar_counts = recent_food_counts(nutrition_profile, date)

    scored = []
    for food in candidates.iterator():
        if food.id in already_today or not _is_ready_to_eat(food) or staples.is_odd(food):
            continue
        servings = _suggested_servings(food, ideal_item_cal)
        if food.calories * servings > remaining.calories:
            continue  # never suggest something that blows past the day's goal
        score = _score(food, servings, remaining, ideal_item_cal, familiar_counts.get(food.id, 0))
        scored.append(
            Suggestion(
                food=food,
                servings=servings,
                calories=round(food.calories * servings, 1),
                protein_g=round(food.protein_g * servings, 1),
                carbs_g=round(food.carbs_g * servings, 1),
                fat_g=round(food.fat_g * servings, 1),
                amount_label=_amount_label(food, servings),
                score=score,
            )
        )

    scored.sort(key=lambda s: (-s.score, staples.variety_key(s.food, date), s.food.name))

    picked, per_category = [], {}
    for s in scored:
        if per_category.get(s.food.category, 0) >= MAX_PER_CATEGORY:
            continue
        per_category[s.food.category] = per_category.get(s.food.category, 0) + 1
        picked.append(s)
        if len(picked) >= limit:
            break

    for s in picked:
        s.reason = _templated_reason(s, remaining)
    return remaining, picked
