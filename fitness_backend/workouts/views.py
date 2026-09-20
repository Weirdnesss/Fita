from django.db.models import Count, Q
from django.db.models.functions import TruncDate
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import PerformedExercise, TemplateExercise, TemplateHistory, WeightUnit, WgerExercise, WorkoutTemplate
from .serializers import (
    FinishWorkoutSerializer,
    TemplateHistorySerializer,
    WorkoutTemplateSerializer,
)
from .services.workout_generator import (
    WorkoutGenerationRateLimitedError,
    WorkoutGeneratorError,
    generate_workout,
    swap_exercise,
)


GENERATED_TEMPLATE_ERROR = {
    "error": "Generated routines can't be edited directly. Delete it and tap Generate again for a new one."
}


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
        if template.is_generated:
            return Response(GENERATED_TEMPLATE_ERROR, status=status.HTTP_403_FORBIDDEN)

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

        target_sets = request.data.get("target_sets", 3)
        try:
            target_sets = int(target_sets)
        except (TypeError, ValueError):
            return Response(
                {"error": "target_sets must be an integer"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if target_sets < 1:
            return Response(
                {"error": "target_sets must be at least 1"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        cached = WgerExercise.objects.filter(id=wger_exercise_id).first()
        if not cached:
            return Response(
                {
                    "error": "Exercise not found in local cache. Run "
                    "'python manage.py sync_wger_exercises' or pick a different exercise."
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        weight_unit = request.data.get("weight_unit")
        if weight_unit not in (WeightUnit.KG, WeightUnit.LB):
            weight_unit = (
                WeightUnit.LB
                if "dumbbell" in cached.equipment_name.lower()
                else WeightUnit.KG
            )

        exercise = template.exercises.create(
            wger_exercise_id=wger_exercise_id,
            exercise_name=cached.name,
            category_name=cached.category_name,
            equipment_name=cached.equipment_name,
            target_sets=target_sets,
            order=template.exercises.count(),
            weight_unit=weight_unit,
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

    def patch(self, request, template_id, exercise_id):
        template, exercise = self.get_exercise(request, template_id, exercise_id)
        if template.is_generated:
            return Response(GENERATED_TEMPLATE_ERROR, status=status.HTTP_403_FORBIDDEN)

        update_fields = []

        if "target_sets" in request.data:
            try:
                target_sets = int(request.data.get("target_sets"))
            except (TypeError, ValueError):
                return Response(
                    {"error": "target_sets must be an integer"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if target_sets < 1:
                return Response(
                    {"error": "target_sets must be at least 1"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
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

        if not update_fields:
            return Response(
                {"error": "Provide target_sets and/or weight_unit to update"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        exercise.save(update_fields=update_fields)
        return Response(WorkoutTemplateSerializer(template).data)

    def delete(self, request, template_id, exercise_id):
        template, exercise = self.get_exercise(request, template_id, exercise_id)
        if template.is_generated:
            return Response(GENERATED_TEMPLATE_ERROR, status=status.HTTP_403_FORBIDDEN)
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
                weight_unit=ex.get("weight_unit") or WeightUnit.KG,
            )
        return Response(
            TemplateHistorySerializer(history).data, status=status.HTTP_201_CREATED
        )


class WorkoutHistoryDetailView(generics.RetrieveAPIView):
    """
    GET /workouts/history/<id>/ -- one completed session, with every
    logged exercise and its sets. Used by the read-only history detail
    page.
    """

    serializer_class = TemplateHistorySerializer

    def get_queryset(self):
        return TemplateHistory.objects.filter(user=self.request.user)


class GenerateWorkoutView(APIView):
    """
    POST /workouts/generate/
    The "Generate Workout" dashboard button. Reads the user's Profile
    (goal, workout frequency, workout location) and (re)generates
    every day-type template in their split at once -- e.g. both Upper
    and Lower together -- see workouts/services/workout_generator.py
    for the actual rules, including the once-per-7-days cooldown and
    the stagnation check that decides whether a day-type's exercises
    actually get reshuffled.
    Response: {"templates": [...]}
    A 429 response (rate limited) includes "next_eligible_at".
    """

    def post(self, request):
        try:
            templates = generate_workout(request.user)
        except WorkoutGenerationRateLimitedError as e:
            return Response(
                {"error": str(e), "next_eligible_at": e.next_eligible_at.isoformat()},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        except WorkoutGeneratorError as e:
            return Response({"error": str(e)}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
        return Response({"templates": WorkoutTemplateSerializer(templates, many=True).data})


class TemplateExerciseSwapView(APIView):
    """
    POST /workouts/templates/<template_id>/exercises/<exercise_id>/swap/
    Body: {"reason": "too_hard" | "unavailable" | "wrong"}
    Replaces this one exercise with a different candidate from the
    same category, leaving the rest of the template (and the weekly
    Generate cooldown) untouched. Available on generated templates
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
        start_date = today - timezone.timedelta(days=num_days - 1)

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
            d = start_date + timezone.timedelta(days=i)
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
        previous_start = start_date - timezone.timedelta(days=num_days)
        previous_end = start_date - timezone.timedelta(days=1)
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
        cursor = today if today in logged_dates else today - timezone.timedelta(days=1)
        streak = 0
        while cursor in logged_dates:
            streak += 1
            cursor -= timezone.timedelta(days=1)
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
    One exercise's per-session progression: for each session that
    included it, the heaviest set logged (weight + the reps done at that
    weight) and the total number of sets. This is deliberately simpler
    than an estimated-1RM formula -- "your heaviest set each session" is
    something a beginner can read at a glance, where a 1RM formula needs
    explaining and can be misleading at high rep counts anyway.

    period uses a longer window than the main trends view (30/90 days,
    or all-time) since meaningful strength progression usually isn't
    visible over just 7 days.
    """

    PERIOD_DAYS = {"month": 30, "3months": 90}  # "all" is handled separately (no date filter)

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
            cutoff = timezone.localdate() - timezone.timedelta(days=self.PERIOD_DAYS[period] - 1)
            performed = performed.filter(history__started_at__date__gte=cutoff)

        sessions_by_date = {}
        for p in performed.order_by("history__started_at"):
            d = timezone.localtime(p.history.started_at).date()
            session = sessions_by_date.setdefault(
                d, {"date": d.isoformat(), "top_weight": 0, "top_weight_reps": 0, "total_sets": 0}
            )
            for s in p.sets_data:
                weight = s.get("weight") or 0
                reps = s.get("reps") or 0
                session["total_sets"] += 1
                # "Heaviest set" -- ties broken by more reps at that weight,
                # since that's still meaningfully more work done.
                if weight > session["top_weight"] or (
                    weight == session["top_weight"] and reps > session["top_weight_reps"]
                ):
                    session["top_weight"] = weight
                    session["top_weight_reps"] = reps

        sessions = sorted(sessions_by_date.values(), key=lambda s: s["date"])

        return Response({
            "exercise": exercise_name,
            "period": period,
            "sessions": sessions,
        })