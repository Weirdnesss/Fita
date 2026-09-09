from django.db import models


class ResourceCategory(models.TextChoices):
    WORKOUT = "workout", "Workout"
    NUTRITION = "nutrition", "Nutrition"
    GENERAL = "general", "General"


class Resource(models.Model):
    """
    A curated link to an external article/video/etc, browsable in-app.
    This is a global catalog (like FoodItem/WgerExercise), not per-user
    data -- populate it via Django admin. Read-only from the API.
    """

    title = models.CharField(max_length=200)
    summary = models.CharField(max_length=300, blank=True)
    category = models.CharField(
        max_length=10, choices=ResourceCategory.choices, default=ResourceCategory.GENERAL
    )
    url = models.URLField()
    source = models.CharField(max_length=100, blank=True, help_text="e.g. 'Healthline', 'NASM'")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title