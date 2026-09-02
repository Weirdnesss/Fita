from django.utils import timezone
from rest_framework import serializers

from .models import PerformedExercise, TemplateExercise, TemplateHistory, WeightUnit, WorkoutTemplate


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
            "weight_unit",
        ]


class WorkoutTemplateSerializer(serializers.ModelSerializer):
    exercises = TemplateExerciseSerializer(many=True, read_only=True)

    class Meta:
        model = WorkoutTemplate
        fields = ["id", "title", "kind", "is_generated", "day_type", "exercises", "created_at", "updated_at"]
        read_only_fields = ["is_generated", "day_type"]


class PerformedExerciseSerializer(serializers.ModelSerializer):
    total_sets_performed = serializers.ReadOnlyField()
    total_volume = serializers.ReadOnlyField()

    class Meta:
        model = PerformedExercise
        fields = [
            "id",
            "exercise_name",
            "sets_data",
            "weight_unit",
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
            "note",
            "performed_exercises",
        ]


class LoggedSetSerializer(serializers.Serializer):
    """One logged set. weight is always kg by the time it reaches here
    (the frontend converts lb entries before submitting) -- display_weight
    is the exact number the user typed, in whatever unit was shown, kept
    so history can redisplay it precisely instead of round-tripping
    through a unit conversion and picking up rounding error."""

    weight = serializers.FloatField(min_value=0)
    reps = serializers.IntegerField(min_value=1)
    display_weight = serializers.FloatField(min_value=0, required=False)


class PerformedExerciseInputSerializer(serializers.Serializer):
    exercise_name = serializers.CharField(max_length=200)
    weight_unit = serializers.ChoiceField(choices=WeightUnit.choices, required=False, default=WeightUnit.KG)
    sets_data = LoggedSetSerializer(many=True, required=False, default=list)


class FinishWorkoutSerializer(serializers.Serializer):
    """Payload shape for POST /workouts/history/  (Finish Workout button)."""

    template_title = serializers.CharField(max_length=150)
    started_at = serializers.DateTimeField()
    exercises = PerformedExerciseInputSerializer(many=True)
    note = serializers.CharField(max_length=1000, required=False, allow_blank=True, default="")

    def validate_started_at(self, value):
        # No lower bound -- a workout can legitimately be started, left
        # running for a long time (PWA backgrounded, resumed days later),
        # and finished much later; that's a long session, not a bug.
        # But it can never be in the future -- small tolerance for
        # client/server clock skew, reject anything clearly beyond that.
        if value > timezone.now() + timezone.timedelta(minutes=5):
            raise serializers.ValidationError("started_at can't be in the future.")
        return value

    def validate_exercises(self, value):
        # Each exercise's sets_data has already been type/range-checked
        # by LoggedSetSerializer at this point (weight is a non-negative
        # number, reps is a positive integer) -- a malformed or malicious
        # request never reaches the database. What's left here is just
        # dropping exercises with nothing logged: an exercise that was
        # added to the workout but never actually logged shouldn't be
        # saved as a PerformedExercise row.
        with_sets = [ex for ex in value if ex.get("sets_data")]
        if not with_sets:
            raise serializers.ValidationError(
                "Log at least one set before finishing the workout."
            )
        return with_sets