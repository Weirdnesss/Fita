from django.db import transaction
from django.db.models import Count, Q
from django.db.models.functions import TruncDate
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView
from datetime import timedelta

from .models import InputType, PerformedExercise, TemplateExercise, TemplateHistory, WeightUnit, WgerExercise, WorkoutTemplate
from .serializers import (
    MAX_EDIT_DAYS,
    REQUIRED_SET_FIELDS,
    EditWorkoutSerializer,
    FinishWorkoutSerializer,
    TemplateHistorySerializer,
    WorkoutTemplateSerializer,
    edit_window_start,
    history_is_editable,
)
from .services.workout_generator import (
    MAX_SETS,
    WorkoutGenerationNotNeededError,
    WorkoutGeneratorError,
    generate_workout,
    get_addable_exercises,
    get_generation_eligibility,
    get_medical_condition_note,
    infer_input_type,
    swap_exercise,
    suggest_exercise_for_template
)


GENERATED_TEMPLATE_ERROR = {
    "error": "Generated routines can't be edited directly. You can swap, add, or remove individual exercises."
}

MIN_GENERATED_EXERCISES = 1
MAX_GENERATED_EXERCISES = 15
MIN_TARGET_SETS = 1
MAX_TARGET_SETS = 10


def parse_target_sets(value):
    """Returns (target_sets, None) if valid, else (None, error Response)."""
    try:
        target_sets = int(value)
    except (TypeError, ValueError):
        return None, Response(
            {"error": "target_sets must be an integer"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if not (MIN_TARGET_SETS <= target_sets <= MAX_TARGET_SETS):
        return None, Response(
            {"error": f"target_sets must be between {MIN_TARGET_SETS} and {MAX_TARGET_SETS}"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return target_sets, None


class ExerciseSearchView(APIView):
    """
    GET /workouts/exercises/search/?q=bench&category=Chest&offset=20
    Searches the local WgerExercise cache -- instant, no external
    call, no rate limits. Run `python manage.py sync_wger_exercises`
    to populate/refresh this cache. If it's empty (never synced),
    this returns an empty list with a hint rather than an error.

    With no q and no category, lists everything (paginated) rather
    than returning empty -- mirrors nutrition.views.FoodSearchView, so
    the exercise picker can show a browsable default list instead of
    requiring the user to type first.

    Paginated via `offset` (default 0), page size PAGE_SIZE --
    response includes `next_offset` (null once there's nothing more
    to load).

    Results include description/equipment_name/muscle_names so a
    client can render a detail view straight from the search response
    without a second request (mirrors FoodSearchView's shape).
    """

    PAGE_SIZE = 20

    def get(self, request):
        term = request.query_params.get("q", "").strip()
        category = request.query_params.get("category", "").strip()

        if not WgerExercise.objects.exists():
            return Response(
                {
                    "count": 0,
                    "results": [],
                    "next_offset": None,
                    "hint": "Exercise database is empty. Run: python manage.py sync_wger_exercises",
                }
            )

        qs = WgerExercise.objects.all()
        if term:
            qs = qs.filter(name__icontains=term)
        if category:
            qs = qs.filter(category_name__iexact=category)

        total = qs.count()
        try:
            offset = int(request.query_params.get("offset", 0))
        except (TypeError, ValueError):
            offset = 0
        offset = max(offset, 0)

        page = qs[offset : offset + self.PAGE_SIZE]
        results = [
            {
                "wger_exercise_id": ex.id,
                "name": ex.name,
                "description": ex.description,
                "category": ex.category_name,
                "equipment": ex.equipment_name,
                "muscles": ex.muscle_names,
            }
            for ex in page
        ]
        next_offset = offset + self.PAGE_SIZE
        return Response({
            "count": total,
            "results": results,
            "next_offset": next_offset if next_offset < total else None,
        })


class ExerciseCategoryListView(APIView):
    """
    GET /workouts/exercises/categories/
    Distinct category names actually present in the synced WgerExercise
    cache (e.g. "Chest", "Back", "Legs") -- fetched dynamically rather
    than hardcoded on the frontend, since these come from wger's data
    and category_name is free text, not a fixed choice set.
    """

    def get(self, request):
        categories = (
            WgerExercise.objects.exclude(category_name="")
            .values_list("category_name", flat=True)
            .distinct()
            .order_by("category_name")
        )
        return Response(list(categories))


class WorkoutTemplateListCreateView(generics.ListCreateAPIView):
    """
    GET  /workouts/templates/   -- list the user's routines (both kinds)
    POST /workouts/templates/   -- create an empty template shell,
                                    then exercises are added via
                                    /workouts/templates/<id>/exercises/
    """

    serializer_class = WorkoutTemplateSerializer

    def get_queryset(self):
        return WorkoutTemplate.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class WorkoutTemplateDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET/PATCH/DELETE /workouts/templates/<id>/
    PATCH is blocked for generated templates (is_generated=True) --
    DELETE is still allowed, since deleting is the intended way to get
    rid of a generated routine you don't want.
    """

    serializer_class = WorkoutTemplateSerializer

    def get_queryset(self):
        return WorkoutTemplate.objects.filter(user=self.request.user)

    def update(self, request, *args, **kwargs):
        if self.get_object().is_generated:
            return Response(GENERATED_TEMPLATE_ERROR, status=status.HTTP_403_FORBIDDEN)
        return super().update(request, *args, **kwargs)


class AddExerciseToTemplateView(APIView):
    """
    POST /workouts/templates/<id>/exercises/
    Body: {"wger_exercise_id": 123, "target_sets": 3, "weight_unit": "kg"}
    Looks up the exercise from the local WgerExercise cache (no live
    wger call needed) and denormalizes name/category onto the
    template exercise row. weight_unit is optional -- if omitted, it
    defaults based on the exercise's equipment (dumbbell exercises
    default to lb, everything else to kg), since that's the common
    real-world split; the user can always override it afterward.
    """

    def post(self, request, template_id):
        template = get_object_or_404(
            WorkoutTemplate, id=template_id, user=request.user
        )

        wger_exercise_id = request.data.get("wger_exercise_id")
        if not wger_exercise_id:
            return Response(
                {"error": "wger_exercise_id is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            wger_exercise_id = int(wger_exercise_id)
        except (TypeError, ValueError):
            return Response(
                {"error": "wger_exercise_id must be an integer"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        target_sets, error = parse_target_sets(request.data.get("target_sets", 3))
        if error:
            return error

        cached = WgerExercise.objects.filter(id=wger_exercise_id).first()
        if not cached:
            return Response(
                {
                    "error": "Exercise not found in local cache. Run "
                    "'python manage.py sync_wger_exercises' or pick a different exercise."
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        if template.is_generated:
            if template.exercises.count() >= MAX_GENERATED_EXERCISES:
                return Response(
                    {"error": f"A routine can have at most {MAX_GENERATED_EXERCISES} exercises."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            _, allowed = get_addable_exercises(template)
            if wger_exercise_id not in {ex.id for ex in allowed}:
                return Response(
                    {"error": "That exercise can't be added to this routine."},
                    status=status.HTTP_422_UNPROCESSABLE_ENTITY,
                )
            # Keep set count consistent with the generated plan.
            first = template.exercises.first()
            target_sets = first.target_sets if first else MAX_SETS

        weight_unit = request.data.get("weight_unit")
        if weight_unit not in (WeightUnit.KG, WeightUnit.LB):
            weight_unit = (
                WeightUnit.LB
                if "dumbbell" in cached.equipment_name.lower()
                else WeightUnit.KG
            )

        template.exercises.create(
            wger_exercise_id=wger_exercise_id,
            exercise_name=cached.name,
            category_name=cached.category_name,
            equipment_name=cached.equipment_name,
            target_sets=target_sets,
            order=template.exercises.count(),
            weight_unit=weight_unit,
            input_type=infer_input_type(cached.name, cached.category_name, cached.equipment_name),
        )
        return Response(
            WorkoutTemplateSerializer(template).data,
            status=status.HTTP_201_CREATED,
        )

class TemplateExerciseSuggestionsView(APIView):
    """
    GET /workouts/templates/<template_id>/exercises/suggestions/?category=Chest&q=press
    Beginner-safe exercises the user can add to a GENERATED template --
    the picker for generated routines uses this instead of the global
    exercise search. Same result shape as ExerciseSearchView, plus the
    categories available for this routine's day-type (for filter chips).
    Not paginated: the safe pool per day-type is small.
    """

    def get(self, request, template_id):
        template = get_object_or_404(
            WorkoutTemplate, id=template_id, user=request.user
        )
        if not template.is_generated:
            return Response(
                {"error": "Suggestions are only for generated routines. Use the exercise search instead."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        categories, results = get_addable_exercises(
            template,
            category=request.query_params.get("category", "").strip(),
            term=request.query_params.get("q", "").strip(),
        )
        return Response({
            "categories": categories,
            "results": [
                {
                    "wger_exercise_id": ex.id,
                    "name": ex.name,
                    "description": ex.description,
                    "category": ex.category_name,
                    "equipment": ex.equipment_name,
                    "muscles": ex.muscle_names,
                }
                for ex in results
            ],
        })

class SuggestExerciseView(APIView):
    """
    POST /workouts/templates/<template_id>/exercises/suggest/
    Adds one auto-picked beginner-safe exercise to a GENERATED template
    (see suggest_exercise_for_template). The user can remove it afterward.
    Response: the updated template.
    """

    def post(self, request, template_id):
        template = get_object_or_404(
            WorkoutTemplate, id=template_id, user=request.user
        )
        if not template.is_generated:
            return Response(
                {"error": "Suggestions are only for generated routines."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if template.exercises.count() >= MAX_GENERATED_EXERCISES:
            return Response(
                {"error": f"A routine can have at most {MAX_GENERATED_EXERCISES} exercises."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            picked = suggest_exercise_for_template(template)
        except WorkoutGeneratorError as e:
            return Response({"error": str(e)}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)

        first = template.exercises.first()
        template.exercises.create(
            wger_exercise_id=picked.id,
            exercise_name=picked.name,
            category_name=picked.category_name,
            equipment_name=picked.equipment_name,
            target_sets=first.target_sets if first else MAX_SETS,
            order=template.exercises.count(),
            weight_unit=(
                WeightUnit.LB if "dumbbell" in picked.equipment_name.lower() else WeightUnit.KG
            ),
            input_type=infer_input_type(picked.name, picked.category_name, picked.equipment_name),
        )
        return Response(
            WorkoutTemplateSerializer(template).data,
            status=status.HTTP_201_CREATED,
        )

class TemplateExerciseDetailView(APIView):
    """
    PATCH  /workouts/templates/<template_id>/exercises/<exercise_id>/
           Body: {"target_sets": 4} and/or {"weight_unit": "lb"}
           Either or both fields can be sent in the same request.
    DELETE /workouts/templates/<template_id>/exercises/<exercise_id>/
           Removes the exercise and re-sequences the remaining
           exercises' `order` values so there's no gap left behind.
    """

    def get_exercise(self, request, template_id, exercise_id):
        template = get_object_or_404(
            WorkoutTemplate, id=template_id, user=request.user
        )
        exercise = get_object_or_404(
            TemplateExercise, id=exercise_id, template=template
        )
        return template, exercise

    # weight_unit and input_type are logging preferences, not changes to the
    # routine itself, so both stay editable on generated routines
    # (target_sets is not).
    GENERATED_EDITABLE = {"weight_unit", "input_type"}

    def patch(self, request, template_id, exercise_id):
        template, exercise = self.get_exercise(request, template_id, exercise_id)

        only_logging_prefs = set(request.data.keys()) <= self.GENERATED_EDITABLE
        if template.is_generated and not only_logging_prefs:
            return Response(GENERATED_TEMPLATE_ERROR, status=status.HTTP_403_FORBIDDEN)

        update_fields = []

        if "target_sets" in request.data:
            if template.is_generated:
                return Response(GENERATED_TEMPLATE_ERROR, status=status.HTTP_403_FORBIDDEN)
            target_sets, error = parse_target_sets(request.data.get("target_sets"))
            if error:
                return error
            exercise.target_sets = target_sets
            update_fields.append("target_sets")

        if "weight_unit" in request.data:
            weight_unit = request.data.get("weight_unit")
            if weight_unit not in (WeightUnit.KG, WeightUnit.LB):
                return Response(
                    {"error": "weight_unit must be 'kg' or 'lb'"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            exercise.weight_unit = weight_unit
            update_fields.append("weight_unit")

        if "input_type" in request.data:
            input_type = request.data.get("input_type")
            if input_type not in InputType.values:
                return Response(
                    {"error": f"input_type must be one of {list(InputType.values)}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            exercise.input_type = input_type
            update_fields.append("input_type")

        if not update_fields:
            return Response(
                {"error": "Provide target_sets, weight_unit and/or input_type to update"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        exercise.save(update_fields=update_fields)
        return Response(WorkoutTemplateSerializer(template).data)
    def delete(self, request, template_id, exercise_id):
        template, exercise = self.get_exercise(request, template_id, exercise_id)
        if template.is_generated and template.exercises.count() <= MIN_GENERATED_EXERCISES:
            return Response(
                {"error": "A routine needs at least one exercise. Delete the routine instead if you don't want it."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        exercise.delete()

        remaining = template.exercises.order_by("order", "id")
        for index, ex in enumerate(remaining):
            if ex.order != index:
                ex.order = index
                ex.save(update_fields=["order"])

        return Response(WorkoutTemplateSerializer(template).data)


class WorkoutHistoryView(generics.ListAPIView):
    """
    GET  /workouts/history/  -- past completed sessions.
    POST /workouts/history/  -- log a session (the "Finish Workout" button).
    Creates a TemplateHistory plus one PerformedExercise per exercise,
    each holding its logged sets.
    """

    serializer_class = TemplateHistorySerializer

    def get_queryset(self):
        return TemplateHistory.objects.filter(user=self.request.user)

    def post(self, request):
        serializer = FinishWorkoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        history = TemplateHistory.objects.create(
            user=request.user,
            template_title=data["template_title"],
            started_at=data["started_at"],
            note=data.get("note", ""),
        )
        for ex in data["exercises"]:
            PerformedExercise.objects.create(
                history=history,
                exercise_name=ex.get("exercise_name", ""),
                sets_data=ex.get("sets_data", []),
                input_type=ex.get("input_type") or InputType.WEIGHT_REPS,
                weight_unit=ex.get("weight_unit") or WeightUnit.KG,
            )
        return Response(
            TemplateHistorySerializer(history).data, status=status.HTTP_201_CREATED
        )


class WorkoutHistoryDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET    /workouts/history/<id>/ -- one completed session, with every logged exercise and its sets.
    PATCH  /workouts/history/<id>/ -- correct a recent session: the note and/or the sets of exercises that are
           already in it. Only allowed for MAX_EDIT_DAYS after the workout was completed. Exercises can't be
           added or renamed, and the start/finish times never change.
    DELETE /workouts/history/<id>/ -- remove a session. Like deleting a food entry, this is not time-limited.
    """

    serializer_class = TemplateHistorySerializer
    http_method_names = ["get", "patch", "delete", "head", "options"]

    def get_queryset(self):
        return TemplateHistory.objects.filter(user=self.request.user)

    def patch(self, request, *args, **kwargs):
        history = self.get_object()
        if not history_is_editable(history):
            return Response(
                {
                    "error": f"Workouts can only be edited for {MAX_EDIT_DAYS} days after they're finished.",
                    "oldest_editable_date": edit_window_start().isoformat(),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = EditWorkoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        performed = {pe.id: pe for pe in history.performed_exercises.all()}
        updates = []
        seen = set()
        for item in data.get("exercises", []):
            pe = performed.get(item["id"])
            if pe is None:
                return Response(
                    {"error": "That exercise isn't part of this workout."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if pe.id in seen:
                return Response(
                    {"error": "Each exercise can only appear once."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            seen.add(pe.id)

            needed = REQUIRED_SET_FIELDS[pe.input_type]
            cleaned = []
            for s in item["sets_data"]:
                if any(field not in s for field in needed):
                    return Response(
                        {"error": f"Each set of {pe.exercise_name} needs: {', '.join(needed)}."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                # Keep only the fields that belong to this exercise's input type.
                keep = set(needed) | ({"display_weight"} if "weight" in needed else set())
                cleaned.append({k: v for k, v in s.items() if k in keep})
            updates.append((pe, cleaned))

        with transaction.atomic():
            if "note" in data:
                history.note = data["note"]
                history.save(update_fields=["note"])
            for pe, cleaned in updates:
                pe.sets_data = cleaned
                pe.save(update_fields=["sets_data"])

        history = self.get_queryset().get(pk=history.pk)
        return Response(TemplateHistorySerializer(history).data)


class GenerateWorkoutView(APIView):
    """
    POST /workouts/generate/
    The "Generate" dashboard button. Reads the user's Profile (goal,
    workout frequency, workout location) and creates or updates every
    day-type template in their split at once -- e.g. both Upper and
    Lower together -- see workouts/services/workout_generator.py for the
    actual rules. Generation only runs when it would change something:
    the first time, after goal/frequency/location change, or when a
    generated routine is missing. Otherwise it returns 409.
    Response: {"templates": [...], "medical_note": "..." | null}
    """

    def post(self, request):
        try:
            templates = generate_workout(request.user)
        except WorkoutGenerationNotNeededError as e:
            return Response({"error": str(e)}, status=status.HTTP_409_CONFLICT)
        except WorkoutGeneratorError as e:
            return Response({"error": str(e)}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
        return Response({
            "templates": WorkoutTemplateSerializer(templates, many=True).data,
            "medical_note": get_medical_condition_note(getattr(request.user, "profile", None)),
        })

class GenerationEligibilityView(APIView):
    """
    GET /workouts/generate/eligibility/
    Read-only counterpart to POST /workouts/generate/ -- lets the
    dashboard show the Generate button's state upfront.
    Response: {"eligible": bool,
               "reason": "first" | "profile_changed" | "missing" | "up_to_date"}
    """

    def get(self, request):
        return Response(get_generation_eligibility(request.user))

class TemplateExerciseSwapView(APIView):
    """
    POST /workouts/templates/<template_id>/exercises/<exercise_id>/swap/
    Body: {"reason": "too_hard" | "unavailable" | "wrong"}
    Replaces this one exercise with a different candidate from the
    same category. Available on generated templates
    even though they otherwise block direct edits -- this is the
    intended way to fix a single bad pick without waiting a week or
    losing the rest of the routine.
    """

    REASONS = {"too_hard", "unavailable", "wrong"}

    def post(self, request, template_id, exercise_id):
        template = get_object_or_404(
            WorkoutTemplate, id=template_id, user=request.user
        )
        exercise = get_object_or_404(
            TemplateExercise, id=exercise_id, template=template
        )

        reason = request.data.get("reason")
        if reason not in self.REASONS:
            return Response(
                {"error": f"reason must be one of {sorted(self.REASONS)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            swap_exercise(template, exercise)
        except WorkoutGeneratorError as e:
            return Response({"error": str(e)}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)

        return Response(WorkoutTemplateSerializer(template).data)

class WorkoutTrendsView(APIView):
    """
    GET /workouts/trends/?period=week|month
    Mirrors nutrition.views.NutritionTrendsView -- aggregates the trailing
    7 (week) or 30 (month) days into per-day workout count and total
    volume (sum of weight*reps across every set logged that day), plus a
    streak and averages, for the Workouts Trends tab.

    Volume is computed from sets_data, which is always stored in kg
    regardless of which unit the user was viewing/entering in at the
    time (see PerformedExercise.weight_unit's docstring) -- so no unit
    conversion is needed here.

    Averages are computed over days that actually have a completed
    workout, not every day in the period -- same reasoning as nutrition's
    averages: including rest days would understate real training load
    and isn't useful feedback.
    """

    PERIOD_DAYS = {"week": 7, "month": 30}

    def get(self, request):
        period = request.query_params.get("period", "week")
        num_days = self.PERIOD_DAYS.get(period)
        if num_days is None:
            return Response(
                {"error": f"period must be one of {list(self.PERIOD_DAYS)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        today = timezone.localdate()
        start_date = today - timedelta(days=num_days - 1)

        histories = (
            TemplateHistory.objects.filter(
                user=request.user,
                started_at__date__gte=start_date,
                started_at__date__lte=today,
            )
            .prefetch_related("performed_exercises")
        )

        by_date = {}
        for history in histories:
            d = timezone.localtime(history.started_at).date()
            bucket = by_date.setdefault(d, {"workouts": 0, "volume": 0.0, "sets": 0})
            bucket["workouts"] += 1
            for performed in history.performed_exercises.all():
                for s in performed.sets_data:
                    weight = s.get("weight") or 0
                    reps = s.get("reps") or 0
                    bucket["volume"] += weight * reps
                    bucket["sets"] += 1

        days = []
        for i in range(num_days):
            d = start_date + timedelta(days=i)
            b = by_date.get(d)
            days.append({
                "date": d.isoformat(),
                "workouts": b["workouts"] if b else 0,
                "volume": round(b["volume"], 1) if b else 0,
                "sets": b["sets"] if b else 0,
                "logged": b is not None,
            })

        logged_days = [d for d in days if d["logged"]]
        days_logged = len(logged_days)

        def avg(field):
            return round(sum(d[field] for d in logged_days) / days_logged, 1) if days_logged else 0

        total_volume = round(sum(d["volume"] for d in days), 1)
        previous_start = start_date - timedelta(days=num_days)
        previous_end = start_date - timedelta(days=1)
        previous_period_volume = round(self._total_volume(request.user, previous_start, previous_end), 1)
        volume_change_pct = (
            round((total_volume - previous_period_volume) / previous_period_volume * 100)
            if previous_period_volume > 0
            else None  # no prior data to compare against -- frontend shows nothing rather than a misleading "+inf%"
        )

        return Response({
            "period": period,
            "days": days,
            "days_logged": days_logged,
            "total_workouts": sum(d["workouts"] for d in days),
            "total_volume": total_volume,
            "previous_period_volume": previous_period_volume,
            "volume_change_pct": volume_change_pct,
            "averages": {
                "volume": avg("volume"),
                "sets": avg("sets"),
            },
            "current_streak": self._current_streak(request.user, today),
        })

    def _total_volume(self, user, start_date, end_date):
        total = 0.0
        performed = PerformedExercise.objects.filter(
            history__user=user,
            history__started_at__date__gte=start_date,
            history__started_at__date__lte=end_date,
        )
        for p in performed:
            for s in p.sets_data:
                total += (s.get("weight") or 0) * (s.get("reps") or 0)
        return total

    def _current_streak(self, user, today):
        # Consecutive days with at least one completed workout, walking
        # backward from today. If today has nothing logged yet, start
        # counting from yesterday instead -- today isn't "over" yet, so
        # not having trained by noon shouldn't zero out an otherwise-
        # intact streak. Mirrors NutritionTrendsView._current_streak.
        logged_dates = set(
            TemplateHistory.objects.filter(user=user)
            .annotate(day=TruncDate("started_at"))
            .values_list("day", flat=True)
            .distinct()
        )
        cursor = today if today in logged_dates else today - timedelta(days=1)
        streak = 0
        while cursor in logged_dates:
            streak += 1
            cursor -= timedelta(days=1)
        return streak


class ExerciseFrequencyView(APIView):
    """
    GET /workouts/trends/exercises/
    Lists the user's most-logged exercises (all-time), for populating the
    exercise picker on the Trends page's progression chart. Sessions
    count = number of distinct completed workouts that included the
    exercise, not number of sets, so it reflects "how often do I train
    this" rather than volume.
    """

    LIMIT = 15

    def get(self, request):
        rows = (
            PerformedExercise.objects.filter(history__user=request.user)
            .values("exercise_name")
            .annotate(sessions=Count("history", distinct=True))
            .order_by("-sessions", "exercise_name")[: self.LIMIT]
        )
        return Response([{"name": r["exercise_name"], "sessions": r["sessions"]} for r in rows])

class ExerciseProgressionView(APIView):
    """
    GET /workouts/trends/exercise/?name=<exercise name>&period=month|3months|all
    One exercise's per-session progression. What counts as "best" depends on
    how the exercise is logged (the most recent entry's input_type decides):
      weight_reps -> heaviest set (weight + the reps done at that weight)
      reps        -> most reps in a single set
      time        -> longest single set, in seconds
    This is deliberately simpler than an estimated-1RM formula -- "your best
    set each session" is something a beginner can read at a glance.

    period uses a longer window than the main trends view (30/90 days,
    or all-time) since meaningful progression usually isn't visible over
    just 7 days.
    """

    PERIOD_DAYS = {"month": 30, "3months": 90}  # "all" is handled separately (no date filter)
    METRIC_FIELD = {
        InputType.WEIGHT_REPS: "top_weight",
        InputType.REPS: "top_reps",
        InputType.TIME: "top_seconds",
    }

    def get(self, request):
        exercise_name = request.query_params.get("name")
        if not exercise_name:
            return Response({"error": "name is required"}, status=status.HTTP_400_BAD_REQUEST)

        period = request.query_params.get("period", "3months")
        if period != "all" and period not in self.PERIOD_DAYS:
            return Response(
                {"error": f"period must be one of {list(self.PERIOD_DAYS) + ['all']}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        performed = (
            PerformedExercise.objects.filter(history__user=request.user, exercise_name=exercise_name)
            .select_related("history")
        )
        if period != "all":
            cutoff = timezone.localdate() - timedelta(days=self.PERIOD_DAYS[period] - 1)
            performed = performed.filter(history__started_at__date__gte=cutoff)

        input_type = InputType.WEIGHT_REPS
        sessions_by_date = {}
        for p in performed.order_by("history__started_at"):
            input_type = p.input_type  # ends as the most recent entry's type
            d = timezone.localtime(p.history.started_at).date()
            session = sessions_by_date.setdefault(
                d,
                {
                    "date": d.isoformat(),
                    "top_weight": 0,
                    "top_weight_reps": 0,
                    "top_reps": 0,
                    "top_seconds": 0,
                    "total_sets": 0,
                },
            )
            for s in p.sets_data:
                weight = s.get("weight") or 0
                reps = s.get("reps") or 0
                seconds = s.get("seconds") or 0
                session["total_sets"] += 1
                session["top_reps"] = max(session["top_reps"], reps)
                session["top_seconds"] = max(session["top_seconds"], seconds)
                # "Heaviest set" -- ties broken by more reps at that weight,
                # since that's still meaningfully more work done.
                if weight > session["top_weight"] or (
                    weight == session["top_weight"] and reps > session["top_weight_reps"]
                ):
                    session["top_weight"] = weight
                    session["top_weight_reps"] = reps

        # Sessions logged under a different input type (the user switched it
        # later) have nothing to chart for this metric, so they're skipped.
        metric = self.METRIC_FIELD[input_type]
        sessions = sorted(
            (s for s in sessions_by_date.values() if input_type == InputType.WEIGHT_REPS or s[metric] > 0),
            key=lambda s: s["date"],
        )

        return Response({
            "exercise": exercise_name,
            "period": period,
            "input_type": input_type,
            "sessions": sessions,
        })