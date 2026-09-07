from django.urls import path

from .views import (
    AddExerciseToTemplateView,
    ExerciseSearchView,
    GenerateWorkoutView,
    TemplateExerciseDetailView,
    TemplateExerciseSwapView,
    WorkoutHistoryDetailView,
    WorkoutHistoryView,
    WorkoutTemplateDetailView,
    WorkoutTemplateListCreateView,
)

urlpatterns = [
    path("exercises/search/", ExerciseSearchView.as_view(), name="exercise-search"),
    path("templates/", WorkoutTemplateListCreateView.as_view(), name="template-list"),
    path("templates/<int:pk>/", WorkoutTemplateDetailView.as_view(), name="template-detail"),
    path(
        "templates/<int:template_id>/exercises/",
        AddExerciseToTemplateView.as_view(),
        name="template-add-exercise",
    ),
    path(
        "templates/<int:template_id>/exercises/<int:exercise_id>/",
        TemplateExerciseDetailView.as_view(),
        name="template-exercise-detail",
    ),
    path(
        "templates/<int:template_id>/exercises/<int:exercise_id>/swap/",
        TemplateExerciseSwapView.as_view(),
        name="template-exercise-swap",
    ),
    path("history/", WorkoutHistoryView.as_view(), name="history"),
    path("history/<int:pk>/", WorkoutHistoryDetailView.as_view(), name="history-detail"),
    path("generate/", GenerateWorkoutView.as_view(), name="generate-workout"),
]