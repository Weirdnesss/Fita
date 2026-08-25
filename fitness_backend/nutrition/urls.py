from django.urls import path

from .views import (
    DailyEntryView,
    FoodEntryCreateView,
    FoodEntryDeleteView,
    FoodSearchView,
    NutritionProfileView,
)

urlpatterns = [
    path("foods/search/", FoodSearchView.as_view(), name="food-search"),
    path("profile/", NutritionProfileView.as_view(), name="nutrition-profile"),
    path("daily/", DailyEntryView.as_view(), name="daily-entry"),
    path("entries/", FoodEntryCreateView.as_view(), name="entry-create"),
    path("entries/<int:pk>/", FoodEntryDeleteView.as_view(), name="entry-delete"),
]
