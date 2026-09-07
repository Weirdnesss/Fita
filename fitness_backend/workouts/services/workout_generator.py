"""
Rule-based workout generator, backing the "Generate Workout" dashboard
button. Same "algorithm thinks, humanized output shown" spirit as the
nutrition/progress rule engines -- no LLM involved here, just profile
data (plus logged history) mapped to a split, category set, and
exercise pool.

Split is chosen from Profile.workout_frequency:
    1-2 days/week  -> Full Body
    3-4 days/week  -> Upper / Lower
    5-6 or daily   -> Push / Pull / Legs

One "Generate" click (re)generates every day-type in that split at
once (e.g. both Upper and Lower together), rather than one day-type
per click. It's capped to once every 7 days account-wide via
WorkoutGenerationState -- see generate_workout(). A DB constraint
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

Because generation is rate-limited to once/week, a regenerate doesn't
reshuffle exercises by default -- see _is_stagnant(). Reshuffling only
happens for a day-type whose logged volume hasn't improved across its
last 3 sessions; otherwise the existing exercises are left alone so a
beginner keeps practicing (and progressing on) what's already working.
Swapping a single exercise (too hard / equipment unavailable / not
appropriate) is a separate, unrestricted path -- see swap_exercise().
"""

import random
from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from accounts.models import PrimaryGoal, WorkoutFrequency, WorkoutLocation
from ..models import (
    DayType,
    TemplateExercise,
    TemplateHistory,
    TemplateKind,
    WeightUnit,
    WgerExercise,
    WorkoutGenerationState,
    WorkoutTemplate,
)


class WorkoutGeneratorError(Exception):
    """Raised when a workout can't be generated (empty cache, no matches)."""


class WorkoutGenerationRateLimitedError(WorkoutGeneratorError):
    """
    Raised when Generate is used again before the weekly cooldown has
    elapsed. Carries next_eligible_at so the view/frontend can show
    exactly when the button unlocks, instead of just "try later".
    """

    def __init__(self, next_eligible_at):
        self.next_eligible_at = next_eligible_at
        super().__init__(
            f"Workouts can only be generated once every 7 days. "
            f"Next available: {next_eligible_at.isoformat()}."
        )


GENERATION_COOLDOWN = timedelta(days=7)

# How many of a day-type's most recent logged sessions to look at when
# deciding whether it's stagnant. Fewer than this many sessions logged
# means there isn't enough data to judge progress yet, so the existing
# exercises are left as-is rather than guessing.
STAGNATION_LOOKBACK_SESSIONS = 3

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
# beginner (see module docstring), so target_sets is still capped by
# MAX_SETS below regardless of what a goal asks for here -- kept as a
# separate step rather than baked into these numbers so the cap's
# reasoning stays visible and adjustable on its own.
GOAL_PARAMS = {
    PrimaryGoal.BUILD_STRENGTH: (1, 5),
    PrimaryGoal.GAIN_MUSCLE: (2, 4),
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
        "lat pulldown", "seated row", "bent over row", "pull-up", "pull up",
        "cable row", "deadlift",
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
        "triceps extension", "skull crusher",
    ],
    "Abs": [
        "plank", "crunch", "sit-up", "sit up", "leg raise", "russian twist",
        "cable crunch",
    ],
    "Calves": ["calf raise"],
}


def _pick_exercises_for_category(category, location, count, exclude_ids=None):
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

    if exclude_ids:
        # Used for stagnation reshuffles and single-exercise swaps, so
        # the result is actually different from what's already there.
        # Falls back to allowing the exclusion to be ignored if it
        # would wipe out the whole category (small pools like Calves) --
        # a repeated exercise beats no exercise for that muscle group.
        without_excluded = [c for c in candidates if c.id not in exclude_ids]
        candidates = without_excluded if without_excluded else candidates

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

    # Actively steer away from barbell free-weight compounds (harder
    # to learn safely without coaching) in favor of machine/dumbbell/
    # bodyweight options, regardless of what the goal would otherwise
    # prefer.
    non_barbell = [c for c in candidates if "barbell" not in c.equipment_name.lower()]
    if non_barbell:
        candidates = non_barbell

    # Prefer well-known staples for this category, shuffled within
    # their own group so repeated generations still vary -- but a
    # recognizable staple always beats an obscure exercise for the
    # same muscle group when both are available.
    common_keywords = COMMON_EXERCISE_KEYWORDS.get(category, [])
    if common_keywords:
        common = [
            c for c in candidates
            if any(keyword in c.name.lower() for keyword in common_keywords)
        ]
        other = [c for c in candidates if c not in common]
        random.shuffle(common)
        random.shuffle(other)
        candidates = common + other
    else:
        random.shuffle(candidates)

    return candidates[:count]


def _weight_unit_for(wger_ex):
    return WeightUnit.LB if "dumbbell" in wger_ex.equipment_name.lower() else WeightUnit.KG


def _session_volume(history_entry):
    return sum(pe.total_volume for pe in history_entry.performed_exercises.all())


def _is_stagnant(user, template_title):
    """
    Looks at the last STAGNATION_LOOKBACK_SESSIONS sessions logged
    under this day-type's (generated, so deterministic) title.
    Returns False -- i.e. "don't reshuffle" -- when there isn't enough
    history to judge yet. Returns True only when the most recent
    session's total logged volume hasn't beaten the oldest of the
    lookback window, meaning the beginner isn't progressing on the
    current exercises and variety is more useful than continuity.
    """
    sessions = list(
        TemplateHistory.objects.filter(user=user, template_title=template_title)
        .order_by("-completed_at")[:STAGNATION_LOOKBACK_SESSIONS]
    )
    if len(sessions) < STAGNATION_LOOKBACK_SESSIONS:
        return False

    newest_volume = _session_volume(sessions[0])
    oldest_volume = _session_volume(sessions[-1])
    return newest_volume <= oldest_volume


def _populate_template(template, categories, location, count_per_category, target_sets, exclude_ids=None):
    template.exercises.all().delete()
    order = 0
    for category in categories:
        picks = _pick_exercises_for_category(category, location, count_per_category, exclude_ids)
        for wger_ex in picks:
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
def generate_workout(user):
    """
    (Re)generates every day-type template in the user's split, once
    every 7 days account-wide. For a day-type that already has a
    generated template with enough logged history, exercises are only
    reshuffled if that day-type is stagnant (see _is_stagnant) --
    otherwise the existing exercises are left untouched so progressive
    overload isn't interrupted for no reason. Returns the list of
    templates for the whole split.
    """
    if not WgerExercise.objects.exists():
        raise WorkoutGeneratorError(
            "Exercise database is empty. Run 'python manage.py sync_wger_exercises' first."
        )

    state, _ = WorkoutGenerationState.objects.get_or_create(user=user)
    now = timezone.now()
    if state.last_generated_at is not None:
        next_eligible_at = state.last_generated_at + GENERATION_COOLDOWN
        if now < next_eligible_at:
            raise WorkoutGenerationRateLimitedError(next_eligible_at)

    profile = getattr(user, "profile", None)
    frequency = (profile.workout_frequency if profile else "") or WorkoutFrequency.THREE_TO_FOUR
    location = (profile.workout_location if profile else "") or WorkoutLocation.GYM
    goal = (profile.primary_goal if profile else "") or PrimaryGoal.MAINTAIN_WEIGHT

    split = SPLITS.get(frequency, SPLITS[WorkoutFrequency.THREE_TO_FOUR])
    count_per_category, target_sets = GOAL_PARAMS.get(goal, DEFAULT_GOAL_PARAMS)
    target_sets = min(target_sets, MAX_SETS)

    existing_by_day_type = {
        t.day_type: t
        for t in WorkoutTemplate.objects.filter(
            user=user, is_generated=True, day_type__in=split
        )
    }

    templates = []
    for day_type in split:
        categories = DAY_TYPE_CATEGORIES[day_type]
        title = f"{DAY_TYPE_LABELS[day_type]} (Generated)"
        template = existing_by_day_type.get(day_type)

        if template is None:
            # First time this day-type has been generated -- nothing
            # to compare against, so just populate it fresh.
            template = WorkoutTemplate.objects.create(
                user=user,
                title=title,
                kind=TemplateKind.MAIN,
                is_generated=True,
                day_type=day_type,
            )
            _populate_template(template, categories, location, count_per_category, target_sets)
        elif _is_stagnant(user, title):
            exclude_ids = set(
                template.exercises.values_list("wger_exercise_id", flat=True)
            )
            _populate_template(
                template, categories, location, count_per_category, target_sets,
                exclude_ids=exclude_ids,
            )
            template.save(update_fields=["updated_at"])
        else:
            # Not enough history yet, or the current exercises are
            # still producing progress -- leave them alone. Still
            # touch updated_at so this counts as "used" for anything
            # inspecting recency, and re-save title in case labels
            # ever change.
            template.title = title
            template.save(update_fields=["title", "updated_at"])

        templates.append(template)

    state.last_generated_at = now
    state.save(update_fields=["last_generated_at"])

    if all(t.exercises.count() == 0 for t in templates):
        # Every category across the whole split came up empty --
        # extremely unlikely with a populated cache, but don't leave
        # a set of empty generated routines sitting around silently.
        for t in templates:
            t.delete()
        raise WorkoutGeneratorError(
            "Couldn't find any matching exercises. Try syncing the exercise cache again."
        )

    return templates


def swap_exercise(template, exercise):
    """
    Replaces a single exercise within a template with a different
    candidate from the same category, without touching the rest of
    the template or the weekly generation cooldown. Used for the
    too-hard / equipment-unavailable / not-appropriate cases -- the
    reason itself doesn't change the selection logic (there's no data
    to target a specific reason against), it's just captured by the
    view for the user's own context.
    """
    profile = getattr(template.user, "profile", None)
    location = (profile.workout_location if profile else "") or WorkoutLocation.GYM

    exclude_ids = set(
        template.exercises.values_list("wger_exercise_id", flat=True)
    )
    exclude_ids.add(exercise.wger_exercise_id)

    picks = _pick_exercises_for_category(exercise.category_name, location, 1, exclude_ids)
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