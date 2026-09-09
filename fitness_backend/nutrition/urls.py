from django.urls import path

from .views import (
    DailyEntryView,
    FoodEntryCreateView,
    FoodEntryDetailView,
    FoodSearchView,
    NutritionProfileView,
    NutritionTrendsView,
    SuggestedGoalsView,
)

urlpatterns = [
    path("foods/search/", FoodSearchView.as_view(), name="food-search"),
    path("profile/", NutritionProfileView.as_view(), name="nutrition-profile"),
    path("goals/suggested/", SuggestedGoalsView.as_view(), name="suggested-goals"),
    path("daily/", DailyEntryView.as_view(), name="daily-entry"),
    path("entries/", FoodEntryCreateView.as_view(), name="entry-create"),
    path("entries/<int:pk>/", FoodEntryDetailView.as_view(), name="entry-detail"),
    path("trends/", NutritionTrendsView.as_view(), name="nutrition-trends"),
]
