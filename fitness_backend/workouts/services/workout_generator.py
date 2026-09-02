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

experience_level (beginner/intermediate/advanced) adjusts the same
knobs on top of goal: beginners get a hand-maintained exclude list for
technical/Olympic-style movements (wger has no difficulty field to
filter on automatically), a bias toward non-barbell equipment over
goal's own barbell preference, and a lower target_sets cap.
"""

import random

from django.db import transaction
from django.db.models import Q

from accounts.models import ExperienceLevel, PrimaryGoal, WorkoutFrequency, WorkoutLocation
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

# wger has no per-exercise difficulty field at all, so there's no way
# to automatically detect "too advanced for a beginner" -- this is a
# hand-maintained list of technical/coached movements (Olympic lifts
# and similar) to exclude outright for beginners, matched by name
# since that's the only signal available.
BEGINNER_EXCLUDE_KEYWORDS = [
    "clean and jerk", "clean & jerk", "power clean", "hang clean", "clean",
    "snatch", "muscle up", "muscle-up", "pistol squat", "kipping",
]

# Cap on target_sets for beginners regardless of goal -- novices
# progress well on lower volume while they're still learning movement
# patterns, so even a "build_strength" beginner shouldn't jump
# straight to 5 sets.
BEGINNER_MAX_SETS = 3


def _pick_exercises_for_category(category, location, count, prefer_barbell, beginner):
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

    if beginner:
        exclude_q = Q()
        for keyword in BEGINNER_EXCLUDE_KEYWORDS:
            exclude_q |= Q(name__icontains=keyword)
        excluded_names = set(
            WgerExercise.objects.filter(exclude_q).values_list("name", flat=True)
        )
        filtered = [c for c in candidates if c.name not in excluded_names]
        # Don't let the exclude list wipe out an entire category if
        # everything available happens to match -- a filtered-but-risky
        # exercise beats no exercise for that muscle group at all.
        candidates = filtered if filtered else candidates

    if not candidates:
        return []

    # Beginners: actively steer away from barbell free-weight compounds
    # (harder to learn safely without coaching) regardless of what the
    # goal would otherwise prefer -- machine/dumbbell/bodyweight first.
    # Non-beginners: goal's own barbell preference (e.g. build_strength)
    # applies as designed.
    if beginner:
        non_barbell = [c for c in candidates if "barbell" not in c.equipment_name.lower()]
        if non_barbell:
            candidates = non_barbell
    elif prefer_barbell:
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
    # No experience_level answered defaults to intermediate -- neutral,
    # same reasoning as the other blank-profile defaults above (not
    # assuming beginner OR advanced when we don't actually know).
    experience = (profile.experience_level if profile else "") or ExperienceLevel.INTERMEDIATE
    beginner = experience == ExperienceLevel.BEGINNER

    day_type, existing_template = determine_next_day_type(user, frequency)
    categories = DAY_TYPE_CATEGORIES[day_type]
    count_per_category, target_sets, prefer_barbell = GOAL_PARAMS.get(goal, DEFAULT_GOAL_PARAMS)
    if beginner:
        target_sets = min(target_sets, BEGINNER_MAX_SETS)
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
        picks = _pick_exercises_for_category(category, location, count_per_category, prefer_barbell, beginner)
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