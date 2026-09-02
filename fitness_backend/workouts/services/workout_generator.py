"""
Rule-based workout generator, backing the "Generate Workout" dashboard
button. Same "algorithm thinks, humanized output shown" spirit as the
nutrition/progress rule engines -- no LLM involved here, just profile
data mapped to a split, category set, and exercise pool.

Split is chosen from Profile.workout_frequency:
    1-2 days/week  -> Full Body
    3-4 days/week  -> Upper / Lower
    5-6 or daily   -> Push / Pull / Legs

Each "Generate" call regenerates the one template for the next
day-type in that split, in place, rather than creating a new row every
time -- see determine_next_day_type(). A DB constraint
(one_generated_template_per_day_type_per_user) guarantees at most one
generated template per day-type per user regardless of any bug here.

primary_goal only steers exercises-per-category and target_sets (not
rep ranges -- TemplateExercise has no rep-range field), since that's
all the current data model supports.
"""

import random

from django.db import transaction
from django.db.models import Q

from accounts.models import PrimaryGoal, WorkoutFrequency, WorkoutLocation
from ..models import DayType, TemplateExercise, TemplateKind, WeightUnit, WgerExercise, WorkoutTemplate


class WorkoutGeneratorError(Exception):
    """Raised when a workout can't be generated (empty cache, no matches)."""


# Which day-types make up each split, in rotation order.
SPLITS = {
    WorkoutFrequency.ONE_TO_TWO: [DayType.FULL_BODY],
    WorkoutFrequency.THREE_TO_FOUR: [DayType.UPPER, DayType.LOWER],
    WorkoutFrequency.FIVE_TO_SIX: [DayType.PUSH, DayType.PULL, DayType.LEGS],
    WorkoutFrequency.DAILY: [DayType.PUSH, DayType.PULL, DayType.LEGS],
}

# Which wger exercise categories a day-type trains. wger's category
# names don't distinguish biceps/triceps within "Arms", so push/pull
# both draw from the same Arms pool -- a known simplification.
DAY_TYPE_CATEGORIES = {
    DayType.FULL_BODY: ["Chest", "Back", "Legs", "Shoulders", "Arms", "Abs"],
    DayType.UPPER: ["Chest", "Back", "Shoulders", "Arms"],
    DayType.LOWER: ["Legs", "Calves", "Abs"],
    DayType.PUSH: ["Chest", "Shoulders", "Arms"],
    DayType.PULL: ["Back", "Arms"],
    DayType.LEGS: ["Legs", "Calves", "Abs"],
}

DAY_TYPE_LABELS = dict(DayType.choices)

# Equipment considered available for a home workout. Gym-only gear
# (Barbell, Bench, Incline bench, Pull-up bar, SZ-Bar) is excluded.
HOME_EQUIPMENT = [
    "none (bodyweight exercise)",
    "dumbbell",
    "resistance band",
    "kettlebell",
    "gym mat",
    "swiss ball",
]

# goal -> (exercises per category, target_sets, prefer_barbell)
GOAL_PARAMS = {
    PrimaryGoal.BUILD_STRENGTH: (1, 5, True),
    PrimaryGoal.GAIN_MUSCLE: (2, 4, False),
    PrimaryGoal.LOSE_WEIGHT: (2, 3, False),
    PrimaryGoal.MAINTAIN_WEIGHT: (2, 3, False),
}
DEFAULT_GOAL_PARAMS = (2, 3, False)


def _pick_exercises_for_category(category, location, count, prefer_barbell):
    qs = WgerExercise.objects.filter(category_name__iexact=category)

    if location == WorkoutLocation.HOME:
        home_q = Q()
        for equipment in HOME_EQUIPMENT:
            home_q |= Q(equipment_name__icontains=equipment)
        home_filtered = qs.filter(home_q)
        # Better to offer a gym-equipment exercise for this category
        # than to silently skip it if nothing matches the home list.
        qs = home_filtered if home_filtered.exists() else qs

    candidates = list(qs)
    if not candidates:
        return []

    if prefer_barbell:
        barbell_candidates = [c for c in candidates if "barbell" in c.equipment_name.lower()]
        if barbell_candidates:
            candidates = barbell_candidates

    random.shuffle(candidates)
    return candidates[:count]


def determine_next_day_type(user, frequency):
    """
    Picks which day-type to (re)generate next: any day-type in the
    split that doesn't have a generated template yet (e.g. the user
    deleted it) takes priority; once every day-type has one, the
    least-recently-generated one is replaced, so repeated clicks
    rotate through the whole split rather than always hitting the same
    day-type.
    """
    split = SPLITS.get(frequency, SPLITS[WorkoutFrequency.THREE_TO_FOUR])
    existing = {
        t.day_type: t
        for t in WorkoutTemplate.objects.filter(
            user=user, is_generated=True, day_type__in=split
        )
    }
    for day_type in split:
        if day_type not in existing:
            return day_type, None
    oldest = min(existing.values(), key=lambda t: t.updated_at)
    return oldest.day_type, oldest


@transaction.atomic
def generate_workout(user):
    if not WgerExercise.objects.exists():
        raise WorkoutGeneratorError(
            "Exercise database is empty. Run 'python manage.py sync_wger_exercises' first."
        )

    profile = getattr(user, "profile", None)
    frequency = (profile.workout_frequency if profile else "") or WorkoutFrequency.THREE_TO_FOUR
    location = (profile.workout_location if profile else "") or WorkoutLocation.GYM
    goal = (profile.primary_goal if profile else "") or PrimaryGoal.MAINTAIN_WEIGHT

    day_type, existing_template = determine_next_day_type(user, frequency)
    categories = DAY_TYPE_CATEGORIES[day_type]
    count_per_category, target_sets, prefer_barbell = GOAL_PARAMS.get(goal, DEFAULT_GOAL_PARAMS)
    title = f"{DAY_TYPE_LABELS[day_type]} (Generated)"

    if existing_template:
        template = existing_template
        template.exercises.all().delete()
        template.title = title
        template.save(update_fields=["title"])
    else:
        template = WorkoutTemplate.objects.create(
            user=user,
            title=title,
            kind=TemplateKind.MAIN,
            is_generated=True,
            day_type=day_type,
        )

    order = 0
    for category in categories:
        picks = _pick_exercises_for_category(category, location, count_per_category, prefer_barbell)
        for wger_ex in picks:
            weight_unit = (
                WeightUnit.LB if "dumbbell" in wger_ex.equipment_name.lower() else WeightUnit.KG
            )
            TemplateExercise.objects.create(
                template=template,
                wger_exercise_id=wger_ex.id,
                exercise_name=wger_ex.name,
                category_name=wger_ex.category_name,
                equipment_name=wger_ex.equipment_name,
                target_sets=target_sets,
                order=order,
                weight_unit=weight_unit,
            )
            order += 1

    if template.exercises.count() == 0:
        # Every category came up empty -- extremely unlikely with a
        # populated cache, but don't leave an empty generated routine
        # sitting around silently.
        template.delete()
        raise WorkoutGeneratorError(
            "Couldn't find any matching exercises. Try syncing the exercise cache again."
        )

    return template