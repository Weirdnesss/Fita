from rest_framework import serializers

from .models import PerformedExercise, TemplateExercise, TemplateHistory, WorkoutTemplate


class TemplateExerciseSerializer(serializers.ModelSerializer):
    class Meta:
        model = TemplateExercise
        fields = [
            "id",
            "wger_exercise_id",
            "exercise_name",
            "category_name",
            "equipment_name",
            "target_sets",
            "order",
        ]


class WorkoutTemplateSerializer(serializers.ModelSerializer):
    exercises = TemplateExerciseSerializer(many=True, read_only=True)

    class Meta:
        model = WorkoutTemplate
        fields = ["id", "title", "kind", "exercises", "created_at", "updated_at"]


class PerformedExerciseSerializer(serializers.ModelSerializer):
    total_sets_performed = serializers.ReadOnlyField()
    total_volume = serializers.ReadOnlyField()

    class Meta:
        model = PerformedExercise
        fields = [
            "id",
            "exercise_name",
            "sets_data",
            "total_sets_performed",
            "total_volume",
        ]


class TemplateHistorySerializer(serializers.ModelSerializer):
    performed_exercises = PerformedExerciseSerializer(many=True, read_only=True)
    duration_minutes = serializers.ReadOnlyField()
    total_exercises = serializers.ReadOnlyField()
    total_sets = serializers.ReadOnlyField()

    class Meta:
        model = TemplateHistory
        fields = [
            "id",
            "template_title",
            "started_at",
            "completed_at",
            "duration_minutes",
            "total_exercises",
            "total_sets",
            "performed_exercises",
        ]


class FinishWorkoutSerializer(serializers.Serializer):
    """Payload shape for POST /workouts/history/  (Finish Workout button)."""

    template_title = serializers.CharField(max_length=150)
    started_at = serializers.DateTimeField()
    exercises = serializers.ListField(child=serializers.DictField())
    # each dict: {"exercise_name": str, "sets_data": [{"weight": n, "reps": n}, ...]}
