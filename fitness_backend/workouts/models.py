from django.conf import settings
from django.db import models


class TemplateKind(models.TextChoices):
    MAIN = "main", "My Routine"
    ALTERNATIVE = "alternative", "Alternative Routine"


class DayType(models.TextChoices):
    FULL_BODY = "full_body", "Full Body"
    UPPER = "upper", "Upper Body"
    LOWER = "lower", "Lower Body"
    PUSH = "push", "Push"
    PULL = "pull", "Pull"
    LEGS = "legs", "Legs"


class WorkoutTemplate(models.Model):
    """
    A saved routine, e.g. 'Push Day'. Exercises live on this via
    TemplateExercise. 'kind' distinguishes primary vs. alternative
    routines, matching the two sections on the Workouts dashboard.

    is_generated + day_type back the "Generate Workout" button: one
    click (re)generates every day-type template in the user's split at
    once, each kept as a single row per day-type per user (see
    workouts/services/workout_generator.py), and generated templates
    can't be edited directly (see the is_generated guards in
    views.py) except via the single-exercise swap endpoint.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="templates"
    )
    title = models.CharField(max_length=150)
    kind = models.CharField(
        max_length=15, choices=TemplateKind.choices, default=TemplateKind.MAIN
    )
    is_generated = models.BooleanField(default=False)
    day_type = models.CharField(
        max_length=20, choices=DayType.choices, blank=True, default=""
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "day_type"],
                condition=models.Q(is_generated=True),
                name="one_generated_template_per_day_type_per_user",
            )
        ]

    def __str__(self):
        return f"{self.title} ({self.user.email})"


class WeightUnit(models.TextChoices):
    KG = "kg", "kg"
    LB = "lb", "lb"


class TemplateExercise(models.Model):
    """
    One exercise slot inside a template. Stores a denormalized
    wger_exercise_name/category so the workout still displays
    correctly even if wger is unreachable or the exercise is later
    renamed upstream -- same reasoning as their PerformedExercise
    snapshot pattern.
    """

    template = models.ForeignKey(
        WorkoutTemplate, on_delete=models.CASCADE, related_name="exercises"
    )
    wger_exercise_id = models.IntegerField()
    exercise_name = models.CharField(max_length=200)
    category_name = models.CharField(max_length=100, blank=True)
    equipment_name = models.CharField(max_length=100, blank=True)
    target_sets = models.PositiveSmallIntegerField(default=3)
    order = models.PositiveSmallIntegerField(default=0)
    weight_unit = models.CharField(
        max_length=2, choices=WeightUnit.choices, default=WeightUnit.KG
    )

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return f"{self.exercise_name} in {self.template.title}"


class TemplateHistory(models.Model):
    """A completed workout session, logged when the user hits 'Finish Workout'."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="workout_history"
    )
    template_title = models.CharField(max_length=150)
    started_at = models.DateTimeField()
    completed_at = models.DateTimeField(auto_now_add=True)
    note = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-completed_at"]
        verbose_name_plural = "Template histories"

    @property
    def duration_minutes(self):
        delta = self.completed_at - self.started_at
        return round(delta.total_seconds() / 60, 1)

    @property
    def total_exercises(self):
        return self.performed_exercises.count()

    @property
    def total_sets(self):
        return sum(pe.total_sets_performed for pe in self.performed_exercises.all())

    def __str__(self):
        return f"{self.template_title} - {self.user.email} - {self.completed_at:%Y-%m-%d}"


class PerformedExercise(models.Model):
    """One exercise's logged sets within a completed workout session."""

    history = models.ForeignKey(
        TemplateHistory, on_delete=models.CASCADE, related_name="performed_exercises"
    )
    exercise_name = models.CharField(max_length=200)
    sets_data = models.JSONField(default=list)
    # sets_data weights are always stored in kg, regardless of which
    # unit the user was viewing/entering in -- weight_unit below is a
    # snapshot of the display unit at logging time only, so total_volume
    # math stays correct even if the exercise's unit is changed later.
    weight_unit = models.CharField(
        max_length=2, choices=WeightUnit.choices, default=WeightUnit.KG
    )
    # sets_data example: [{"weight": 40, "reps": 10}, {"weight": 42.5, "reps": 8}]

    @property
    def total_sets_performed(self):
        return len(self.sets_data)

    @property
    def total_volume(self):
        return round(
            sum(s.get("weight", 0) * s.get("reps", 0) for s in self.sets_data), 2
        )

    def __str__(self):
        return f"{self.exercise_name} ({self.history})"


class WorkoutGenerationState(models.Model):
    """
    Tracks the once-per-week cap on the "Generate Workout" button (see
    workouts/services/workout_generator.py). Kept as its own row
    rather than reading WorkoutTemplate.updated_at, since a single
    Generate call can leave some day-types' exercises untouched (no
    stagnation detected, so the existing exercises are kept to protect
    progressive overload) while the click still needs to count against
    the weekly cooldown.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="workout_generation_state",
    )
    last_generated_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"WorkoutGenerationState<{self.user.email}>"


class WgerExercise(models.Model):
    """
    A local cache of wger's exercise database, synced via
    `python manage.py sync_wger_exercises`. Search and lookup happen
    against this table -- instant, no rate limits, works even if
    wger.de is temporarily unreachable or changes its (undocumented)
    search endpoint again. Only English-language entries are cached.
    """

    id = models.IntegerField(primary_key=True, help_text="wger's exercise base_id")
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    category_name = models.CharField(max_length=100, blank=True)
    equipment_name = models.CharField(max_length=200, blank=True)
    muscle_names = models.CharField(max_length=300, blank=True)
    synced_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        indexes = [models.Index(fields=["name"])]

    def __str__(self):
        return self.name