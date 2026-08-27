from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import PerformedExercise, TemplateExercise, TemplateHistory, WeightUnit, WgerExercise, WorkoutTemplate
from .serializers import (
    FinishWorkoutSerializer,
    TemplateHistorySerializer,
    WorkoutTemplateSerializer,
)


class ExerciseSearchView(APIView):
    """
    GET /workouts/exercises/search/?q=bench
    Searches the local WgerExercise cache -- instant, no external
    call, no rate limits. Run `python manage.py sync_wger_exercises`
    to populate/refresh this cache. If it's empty (never synced),
    this returns an empty list with a hint rather than an error.
    """

    def get(self, request):
        term = request.query_params.get("q", "").strip()
        if not term:
            return Response({"results": []})

        if not WgerExercise.objects.exists():
            return Response(
                {
                    "results": [],
                    "hint": "Exercise database is empty. Run: python manage.py sync_wger_exercises",
                }
            )

        matches = WgerExercise.objects.filter(name__icontains=term)[:15]
        results = [
            {
                "wger_exercise_id": ex.id,
                "name": ex.name,
                "category": ex.category_name,
            }
            for ex in matches
        ]
        return Response({"results": results})


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
    """GET/PATCH/DELETE /workouts/templates/<id>/"""

    serializer_class = WorkoutTemplateSerializer

    def get_queryset(self):
        return WorkoutTemplate.objects.filter(user=self.request.user)


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