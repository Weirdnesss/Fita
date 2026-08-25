from django.urls import path

from .views import (
    AddExerciseToTemplateView,
    ExerciseSearchView,
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
    path("history/", WorkoutHistoryView.as_view(), name="history"),
]
