from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import PerformedExercise, TemplateHistory, WgerExercise, WorkoutTemplate
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
    Body: {"wger_exercise_id": 123, "target_sets": 3}
    Looks up the exercise from the local WgerExercise cache (no live
    wger call needed) and denormalizes name/category onto the
    template exercise row.
    """

    def post(self, request, template_id):
        template = get_object_or_404(
            WorkoutTemplate, id=template_id, user=request.user
        )
        wger_exercise_id = request.data.get("wger_exercise_id")
        target_sets = request.data.get("target_sets", 3)
        if not wger_exercise_id:
            return Response(
                {"error": "wger_exercise_id is required"},
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

        exercise = template.exercises.create(
            wger_exercise_id=wger_exercise_id,
            exercise_name=cached.name,
            category_name=cached.category_name,
            equipment_name=cached.equipment_name,
            target_sets=target_sets,
            order=template.exercises.count(),
        )
        return Response(
            WorkoutTemplateSerializer(template).data,
            status=status.HTTP_201_CREATED,
        )


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
        )
        for ex in data["exercises"]:
            PerformedExercise.objects.create(
                history=history,
                exercise_name=ex.get("exercise_name", ""),
                sets_data=ex.get("sets_data", []),
            )
        return Response(
            TemplateHistorySerializer(history).data, status=status.HTTP_201_CREATED
        )
