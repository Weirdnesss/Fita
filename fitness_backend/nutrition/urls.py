from django.urls import path

from .views import (
    CustomFoodCreateView,
    CustomFoodDetailView,
    DailyEntryView,
    FoodEntryBulkCreateView,
    FoodEntryCreateView,
    FoodEntryDetailView,
    FoodSearchView,
    FoodSuggestionsView,
    MealSuggestionsView,
    NutritionProfileView,
    NutritionTrendsView,
    SuggestedGoalsView,
)

urlpatterns = [
    path("foods/search/", FoodSearchView.as_view(), name="food-search"),
    path("foods/custom/", CustomFoodCreateView.as_view(), name="custom-food-create"),
    path("foods/custom/<int:pk>/", CustomFoodDetailView.as_view(), name="custom-food-detail"),
    path("suggestions/", FoodSuggestionsView.as_view(), name="food-suggestions"),
    path("suggestions/meals/", MealSuggestionsView.as_view(), name="meal-suggestions"),
    path("profile/", NutritionProfileView.as_view(), name="nutrition-profile"),
    path("goals/suggested/", SuggestedGoalsView.as_view(), name="suggested-goals"),
    path("daily/", DailyEntryView.as_view(), name="daily-entry"),
    path("entries/", FoodEntryCreateView.as_view(), name="entry-create"),
    path("entries/bulk/", FoodEntryBulkCreateView.as_view(), name="entry-bulk-create"),
    path("entries/<int:pk>/", FoodEntryDetailView.as_view(), name="entry-detail"),
    path("trends/", NutritionTrendsView.as_view(), name="nutrition-trends"),
]
