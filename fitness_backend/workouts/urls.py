from django.urls import path

from .views import (
    AddExerciseToTemplateView,
    ExerciseCategoryListView,
    ExerciseFrequencyView,
    ExerciseProgressionView,
    ExerciseSearchView,
    GenerateWorkoutView,
    TemplateExerciseDetailView,
    TemplateExerciseSwapView,
    WorkoutHistoryDetailView,
    WorkoutHistoryView,
    WorkoutTemplateDetailView,
    WorkoutTemplateListCreateView,
    WorkoutTrendsView,
)

urlpatterns = [
    path("exercises/search/", ExerciseSearchView.as_view(), name="exercise-search"),
    path("exercises/categories/", ExerciseCategoryListView.as_view(), name="exercise-categories"),
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
    path("trends/", WorkoutTrendsView.as_view(), name="workout-trends"),
    path("trends/exercises/", ExerciseFrequencyView.as_view(), name="workout-trends-exercises"),
    path("trends/exercise/", ExerciseProgressionView.as_view(), name="workout-trends-exercise"),
]