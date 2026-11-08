from django.utils import timezone
from rest_framework import serializers

from .models import InputType, PerformedExercise, TemplateExercise, TemplateHistory, WeightUnit, WorkoutTemplate


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
            "input_type",
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
            "input_type",
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
    """One logged set. Which fields are required depends on the exercise's
    input_type (checked in PerformedExerciseInputSerializer.validate).
    weight is always kg by the time it reaches here (the frontend converts
    lb entries before submitting) -- display_weight is the exact number the
    user typed, kept so history can redisplay it without round-trip error."""

    weight = serializers.FloatField(min_value=0, required=False)
    reps = serializers.IntegerField(min_value=1, required=False)
    seconds = serializers.IntegerField(min_value=1, max_value=7200, required=False)
    display_weight = serializers.FloatField(min_value=0, required=False)


REQUIRED_SET_FIELDS = {
    InputType.WEIGHT_REPS: ("weight", "reps"),
    InputType.REPS: ("reps",),
    InputType.TIME: ("seconds",),
}


class PerformedExerciseInputSerializer(serializers.Serializer):
    exercise_name = serializers.CharField(max_length=200)
    input_type = serializers.ChoiceField(choices=InputType.choices, required=False, default=InputType.WEIGHT_REPS)
    weight_unit = serializers.ChoiceField(choices=WeightUnit.choices, required=False, default=WeightUnit.KG)
    sets_data = LoggedSetSerializer(many=True, required=False, default=list)

    def validate(self, attrs):
        needed = REQUIRED_SET_FIELDS[attrs.get("input_type", InputType.WEIGHT_REPS)]
        for s in attrs.get("sets_data", []):
            if any(field not in s for field in needed):
                raise serializers.ValidationError(
                    {"sets_data": f"Each set needs: {', '.join(needed)}."}
                )
        return attrs


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
        # An exercise that was added to the workout but never logged
        # shouldn't be saved as a PerformedExercise row.
        with_sets = [ex for ex in value if ex.get("sets_data")]
        if not with_sets:
            raise serializers.ValidationError(
                "Log at least one set before finishing the workout."
            )
        return with_sets