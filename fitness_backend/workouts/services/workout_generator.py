"""
Rule-based workout generator, backing the dashboard's Generate button.
Same "algorithm thinks, humanized output shown" spirit as the
nutrition/progress rule engines -- no LLM involved here, just profile
data mapped to a split, category set, and exercise pool.

Split is chosen from Profile.workout_frequency:
    1-2 days/week  -> Full Body
    3-4 days/week  -> Upper / Lower
    5-6 or daily   -> Push / Pull / Legs

One "Generate" click creates or updates every day-type in that split at
once. Generate is only available when it would change something (see
_generation_status): the first time, after workout_frequency /
workout_location / primary_goal change, or when a routine in the split
has gone missing. Otherwise existing exercises are left alone so a
beginner keeps practicing what's already in their plan. Swapping a
single exercise (too hard / equipment unavailable / not appropriate) is
a separate path -- see swap_exercise(). A DB constraint
(one_generated_template_per_day_type_per_user) guarantees at most one
generated template per day-type per user regardless of any bug here.

Scoped to gym beginners only (Profile has no experience_level field --
every account is a beginner, matching Objective 2's validation
population). That means exercise selection always applies beginner-
safe logic on top of goal: a hand-maintained exclude list for
technical/Olympic-style movements (wger has no difficulty field to
filter on automatically), a bias toward non-barbell equipment
regardless of goal's own preference, a lower target_sets cap, and a
preference for well-known gym staples over obscure variations.
"""

import random
import re

from django.db import transaction
from django.utils import timezone

from accounts.models import PrimaryGoal, WorkoutFrequency, WorkoutLocation
from ..models import (
    DayType,
    TemplateExercise,
    TemplateKind,
    WeightUnit,
    WgerExercise,
    WorkoutGenerationState,
    WorkoutTemplate,
)


class WorkoutGeneratorError(Exception):
    """Raised when a workout can't be generated (empty cache, no matches)."""


class WorkoutGenerationNotNeededError(WorkoutGeneratorError):
    """
    Raised when Generate is used but nothing would change -- the routines
    already match the user's goal/frequency/location. The view maps this
    to a 409 so the frontend can show the message and sync its button.
    """

    def __init__(self):
        super().__init__(
            "Your routines are already up to date. Change your goal, workout "
            "frequency, or location in your profile to generate a new plan, "
            "or swap individual exercises."
        )


def _profile_params(user):
    profile = getattr(user, "profile", None)
    frequency = (profile.workout_frequency if profile else "") or WorkoutFrequency.THREE_TO_FOUR
    location = (profile.workout_location if profile else "") or WorkoutLocation.GYM
    goal = (profile.primary_goal if profile else "") or PrimaryGoal.MAINTAIN_WEIGHT
    return profile, frequency, location, goal


def _generation_status(user, state, frequency, location, goal):
    """
    Single source of truth for "would Generate change anything?", shared
    by generate_workout() and get_generation_eligibility() so the button
    and the endpoint can never disagree. `state` may be None.

    Returns {"eligible": bool, "reason": "first" | "profile_changed" |
    "missing" | "up_to_date"}.
    """
    split = SPLITS.get(frequency, SPLITS[WorkoutFrequency.THREE_TO_FOUR])
    existing = set(
        WorkoutTemplate.objects.filter(user=user, is_generated=True)
        .values_list("day_type", flat=True)
    )

    if not existing:
        return {"eligible": True, "reason": "first"}

    profile_changed = (
        state is not None
        and state.last_generated_at is not None
        and (
            state.generated_for_frequency != frequency
            or state.generated_for_location != location
            or state.generated_for_goal != goal
        )
    )
    if profile_changed:
        return {"eligible": True, "reason": "profile_changed"}

    if set(split) - existing:
        return {"eligible": True, "reason": "missing"}

    return {"eligible": False, "reason": "up_to_date"}


def get_generation_eligibility(user):
    """
    Read-only: no row creation, no writes. Used by GenerationEligibilityView
    so the dashboard can show the Generate button's state (and why) upfront.
    Returns {"eligible": bool, "reason": str}.
    """
    _, frequency, location, goal = _profile_params(user)
    state = WorkoutGenerationState.objects.filter(user=user).first()
    return _generation_status(user, state, frequency, location, goal)

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

# goal -> (exercises per category, target_sets). Every account is a
# beginner (see module docstring), so target_sets is 3 across the board;
# MAX_SETS below stays as the safety cap if a goal is ever given more.
GOAL_PARAMS = {
    PrimaryGoal.BUILD_STRENGTH: (1, 3),
    PrimaryGoal.GAIN_MUSCLE: (2, 3),
    PrimaryGoal.LOSE_WEIGHT: (2, 3),
    PrimaryGoal.MAINTAIN_WEIGHT: (2, 3),
}
DEFAULT_GOAL_PARAMS = (2, 3)

# wger has no per-exercise difficulty field at all, so there's no way
# to automatically detect "too advanced for a beginner" -- this is a
# hand-maintained list of technical/coached movements (Olympic lifts
# and similar) to exclude outright, matched by name since that's the
# only signal available.
BEGINNER_EXCLUDE_KEYWORDS = [
    "clean and jerk", "clean & jerk", "power clean", "hang clean", "clean",
    "snatch", "muscle up", "muscle-up", "pistol squat", "kipping",
    "behind the neck", "good morning", "upright row", "sissy squat",
    "overhead squat", "jump", "plyo",
]

# Cap on target_sets -- novices progress well on lower volume while
# they're still learning movement patterns, so even a "build_strength"
# goal shouldn't jump straight to 5 sets.
MAX_SETS = 3

# wger has no popularity/usage-frequency field, so there's no way to
# automatically tell a common gym staple from an obscure variation
# that happens to share a category -- this is a hand-maintained list
# of well-known movements per category, matched by name keyword the
# same way BEGINNER_EXCLUDE_KEYWORDS is. It's a preference, not a
# filter: it only reorders candidates so staples get picked first,
# and a category with no keyword matches just falls back to the full
# pool untouched. Skews toward machine/dumbbell/bodyweight staples
# over barbell ones on purpose, since those are also the exercises a
# beginner is most likely to already recognize.
COMMON_EXERCISE_KEYWORDS = {
    "Chest": [
        "bench press", "push-up", "push up", "chest press", "incline press",
        "chest fly", "dumbbell fly", "cable fly",
    ],
    "Back": [
        "lat pulldown", "seated row", "bent over row", "cable row",
    ],
    "Legs": [
        "squat", "leg press", "lunge", "leg extension", "leg curl",
        "romanian deadlift", "step-up", "step up",
    ],
    "Shoulders": [
        "shoulder press", "overhead press", "lateral raise", "front raise",
        "military press", "arnold press",
    ],
    "Arms": [
        "bicep curl", "biceps curl", "dumbbell curl", "hammer curl",
        "tricep pushdown", "triceps pushdown", "tricep extension",
        "triceps extension",
    ],
    "Abs": [
        "plank", "crunch", "sit-up", "sit up", "leg raise", "russian twist",
        "cable crunch",
    ],
    "Calves": ["calf raise"],
}

# Deliberately coarse, whole-category safety net for Profile.medical_conditions
# (free text, matched by keyword the same way BEGINNER_EXCLUDE_KEYWORDS is
# above). This is NOT a substitute for guidance from a doctor or physical
# therapist -- it only recognizes a short list of common, clearly-named
# conditions and reacts at the category level (e.g. drops "Legs" entirely
# for "knee" rather than trying to judge which specific leg exercises are
# knee-safe, which needs real kinesiology judgment this file doesn't have).
# A condition that isn't one of these keywords, or where only some
# exercises in a category are actually a problem, isn't something this can
# safely automate -- see get_medical_condition_note() below, which is
# always shown whenever medical_conditions is non-empty, matched or not.
CONDITION_EXCLUDED_CATEGORIES = {
    "knee": ["Legs"],
    "hip": ["Legs"],
    "ankle": ["Legs", "Calves"],
    "shoulder": ["Shoulders"],
    "back": ["Back"],
    "lower back": ["Back", "Legs"],
    "spine": ["Back", "Legs"],
    "neck": ["Shoulders"],
}

# Same idea, but for specific exercise-name keywords that matter across
# more than one category (e.g. a deadlift is sometimes pulled from the
# Legs pool too, not just Back).
CONDITION_EXCLUDED_EXERCISE_KEYWORDS = {
    "back": ["deadlift"],
    "lower back": ["deadlift"],
    "spine": ["deadlift"],
    "wrist": ["push-up", "push up", "plank"],
}


def _condition_keywords(medical_conditions):
    """Recognized CONDITION_EXCLUDED_* keys found in the user's free-text medical_conditions."""
    if not medical_conditions:
        return []
    text = medical_conditions.lower()
    all_keys = set(CONDITION_EXCLUDED_CATEGORIES) | set(CONDITION_EXCLUDED_EXERCISE_KEYWORDS)
    return [kw for kw in all_keys if re.search(rf"\b{re.escape(kw)}", text)]


def get_medical_condition_note(profile):
    """
    Shown whenever the user has anything in Profile.medical_conditions,
    regardless of whether a recognized keyword was matched -- free text
    can say anything, and this generator can only act on a short known
    list (see CONDITION_EXCLUDED_CATEGORIES), so the disclaimer has to
    cover the gap between "what we filtered" and "what's actually safe
    for this person". Returns None when there's nothing on file.
    """
    if not profile or not profile.medical_conditions:
        return None
    matched = _condition_keywords(profile.medical_conditions)
    if matched:
        avoided = sorted({
            cat for kw in matched for cat in CONDITION_EXCLUDED_CATEGORIES.get(kw, [])
        })
        detail = f" We've tried to avoid {', '.join(avoided)} exercises based on this." if avoided else ""
        return (
            f"Your profile mentions a medical condition or injury.{detail} "
            "This is a basic precaution, not medical advice -- please review this "
            "routine with a doctor or physical therapist before starting."
        )
    return (
        "Your profile mentions a medical condition or injury we don't have "
        "specific exercise guidance for. Please review this routine with a "
        "doctor or physical therapist before starting."
    )


def _name_has_keyword(name, keywords):
    """Word-start match, so 'clean' doesn't hit unrelated words mid-name."""
    name = name.lower()
    return any(re.search(rf"\b{re.escape(k)}", name) for k in keywords)

def _safe_candidates(category, location, exclude_ids=None, extra_exclude_keywords=None):
    """
    The one place beginner safety is decided -- used by both generation
    and swapping, so they can never disagree. No fallbacks: if nothing
    in a category passes, the category yields nothing rather than
    relaxing a rule.
    """
    staples = COMMON_EXERCISE_KEYWORDS.get(category, [])
    if not staples:
        return []

    blocked = list(BEGINNER_EXCLUDE_KEYWORDS) + list(extra_exclude_keywords or [])
    pool = []
    # order_by("id") keeps the pool order stable, so a seeded shuffle is reproducible
    for ex in WgerExercise.objects.filter(category_name__iexact=category).order_by("id"):
        if exclude_ids and ex.id in exclude_ids:
            continue
        if not _name_has_keyword(ex.name, staples):
            continue
        if _name_has_keyword(ex.name, blocked):
            continue
        equipment = (ex.equipment_name or "").lower()
        if "barbell" in equipment:
            continue
        if location == WorkoutLocation.HOME and not any(h in equipment for h in HOME_EQUIPMENT):
            continue
        pool.append(ex)
    return pool

def _pick_exercises_for_category(
    category, location, count, exclude_ids=None, extra_exclude_keywords=None,
    rng=None, strict_exclude=False,
):
    rng = rng or random.Random()
    pool = _safe_candidates(category, location, exclude_ids, extra_exclude_keywords)
    if not pool and exclude_ids and not strict_exclude:
        # A reshuffle may reuse what's already there if nothing else is
        # safe -- it's still from the safe pool. Swaps pass
        # strict_exclude=True and never get the same exercise back.
        pool = _safe_candidates(category, location, None, extra_exclude_keywords)
    rng.shuffle(pool)
    return pool[:count]

def _weight_unit_for(wger_ex):
    return WeightUnit.LB if "dumbbell" in wger_ex.equipment_name.lower() else WeightUnit.KG


def _populate_template(
    template, categories, location, count_per_category, target_sets,
    exclude_ids=None, condition_keywords=None, rng=None,
):
    excluded_categories = set()
    excluded_exercise_keywords = set()
    for kw in (condition_keywords or []):
        excluded_categories.update(CONDITION_EXCLUDED_CATEGORIES.get(kw, []))
        excluded_exercise_keywords.update(CONDITION_EXCLUDED_EXERCISE_KEYWORDS.get(kw, []))

    template.exercises.all().delete()
    order = 0
    used_ids = set()
    for category in categories:
        if category in excluded_categories:
            continue
        picks = _pick_exercises_for_category(
            category, location, count_per_category,
            (exclude_ids or set()) | used_ids,
            extra_exclude_keywords=excluded_exercise_keywords,
            rng=rng,
        )
        for wger_ex in picks:
            if wger_ex.id in used_ids:
                continue
            used_ids.add(wger_ex.id)
            TemplateExercise.objects.create(
                template=template,
                wger_exercise_id=wger_ex.id,
                exercise_name=wger_ex.name,
                category_name=wger_ex.category_name,
                equipment_name=wger_ex.equipment_name,
                target_sets=target_sets,
                order=order,
                weight_unit=_weight_unit_for(wger_ex),
            )
            order += 1
    return template.exercises.count()

@transaction.atomic
def generate_workout(user, seed=None):
    """
    Creates or updates the generated routines for the user's split, but
    only when something would change (see _generation_status). A day-type
    that already exists is left untouched unless goal/frequency/location
    changed, in which case it's reshuffled so the new parameters actually
    take effect. Missing day-types are created fresh. Returns the list of
    templates for the whole split.
    """
    if not WgerExercise.objects.exists():
        raise WorkoutGeneratorError(
            "Exercise database is empty. Run 'python manage.py sync_wger_exercises' first."
        )

    profile, frequency, location, goal = _profile_params(user)
    # Same user + same goal/frequency/location -> same plan. A string seed
    # is deterministic across runs (unlike hash()), so results are
    # reproducible for testing and for demonstrating the algorithm.
    rng = random.Random(seed if seed is not None else f"{user.pk}|{frequency}|{location}|{goal}")

    state, _ = WorkoutGenerationState.objects.get_or_create(user=user)
    # Lock the row so a double-click (or two tabs) can't run two
    # generations at once -- the second waits, then sees "up to date".
    state = WorkoutGenerationState.objects.select_for_update().get(pk=state.pk)

    status = _generation_status(user, state, frequency, location, goal)
    if not status["eligible"]:
        raise WorkoutGenerationNotNeededError()
    profile_changed = status["reason"] == "profile_changed"

    condition_keywords = _condition_keywords(profile.medical_conditions if profile else "")

    split = SPLITS.get(frequency, SPLITS[WorkoutFrequency.THREE_TO_FOUR])
    count_per_category, target_sets = GOAL_PARAMS.get(goal, DEFAULT_GOAL_PARAMS)
    target_sets = min(target_sets, MAX_SETS)

    # No two frequency tiers share a day-type, so a frequency change makes
    # every previously-generated template stale -- prune anything not in
    # the new split. Safe: TemplateHistory snapshots template_title as a
    # plain string, so past logged workouts are unaffected.
    WorkoutTemplate.objects.filter(
        user=user, is_generated=True
    ).exclude(day_type__in=split).delete()

    existing_by_day_type = {
        t.day_type: t
        for t in WorkoutTemplate.objects.filter(
            user=user, is_generated=True, day_type__in=split
        )
    }

    templates = []
    for day_type in split:
        categories = DAY_TYPE_CATEGORIES[day_type]
        title = DAY_TYPE_LABELS[day_type]
        template = existing_by_day_type.get(day_type)

        if template is None:
            template = WorkoutTemplate.objects.create(
                user=user, title=title, kind=TemplateKind.MAIN,
                is_generated=True, day_type=day_type,
            )
            _populate_template(
                template, categories, location, count_per_category, target_sets,
                condition_keywords=condition_keywords, rng=rng,
            )
        else:
            if profile_changed:
                exclude_ids = set(template.exercises.values_list("wger_exercise_id", flat=True))
                _populate_template(
                    template, categories, location, count_per_category, target_sets,
                    exclude_ids=exclude_ids, condition_keywords=condition_keywords, rng=rng,
                )
            template.title = title
            template.save(update_fields=["title", "updated_at"])

        if template.exercises.count() == 0:
            template.delete()  # nothing safe for this day-type -- don't keep an empty routine
            continue
        templates.append(template)

    state.last_generated_at = timezone.now()
    state.generated_for_frequency = frequency
    state.generated_for_location = location
    state.generated_for_goal = goal
    state.save(update_fields=[
        "last_generated_at", "generated_for_frequency", "generated_for_location", "generated_for_goal",
    ])

    if not templates:
        # Raising inside the atomic block also rolls the state update back.
        raise WorkoutGeneratorError(
            "Couldn't find safe exercises that fit your profile. If you have a "
            "medical condition or injury, check with a doctor or physical therapist, "
            "or try syncing the exercise cache again."
        )

    return templates

def swap_exercise(template, exercise):
    """
    Replaces a single exercise within a template with a different
    candidate from the same category, without touching the rest of the
    template. Used for the too-hard / equipment-unavailable /
    not-appropriate cases -- the reason doesn't change the selection
    logic (there's no data to target a specific reason against), it's
    just captured by the view for the user's own context.
    """
    profile = getattr(template.user, "profile", None)
    location = (profile.workout_location if profile else "") or WorkoutLocation.GYM

    excluded_exercise_keywords = set()
    for kw in _condition_keywords(profile.medical_conditions if profile else ""):
        excluded_exercise_keywords.update(CONDITION_EXCLUDED_EXERCISE_KEYWORDS.get(kw, []))

    exclude_ids = set(
        template.exercises.values_list("wger_exercise_id", flat=True)
    )
    exclude_ids.add(exercise.wger_exercise_id)

    picks = _pick_exercises_for_category(
        exercise.category_name, location, 1, exclude_ids,
        extra_exclude_keywords=excluded_exercise_keywords,
        strict_exclude=True,
    )
    if not picks:
        raise WorkoutGeneratorError(
            "No alternative exercise is available for this category right now."
        )

    new_exercise = picks[0]
    exercise.wger_exercise_id = new_exercise.id
    exercise.exercise_name = new_exercise.name
    exercise.category_name = new_exercise.category_name
    exercise.equipment_name = new_exercise.equipment_name
    exercise.weight_unit = _weight_unit_for(new_exercise)
    exercise.save(
        update_fields=[
            "wger_exercise_id", "exercise_name", "category_name",
            "equipment_name", "weight_unit",
        ]
    )
    return exercise