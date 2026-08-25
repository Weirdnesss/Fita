from rest_framework import serializers

from .models import DailyEntry, FoodEntry, FoodItem, NutritionProfile


class FoodItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = FoodItem
        fields = [
            "id",
            "name",
            "local_name",
            "category",
            "serving_description",
            "serving_size_g",
            "calories",
            "protein_g",
            "carbs_g",
            "fat_g",
            "fiber_g",
            "sodium_mg",
            "source",
        ]


class NutritionProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = NutritionProfile
        fields = [
            "daily_calories_goal",
            "daily_protein_goal",
            "daily_carbs_goal",
            "daily_fat_goal",
        ]


class FoodEntrySerializer(serializers.ModelSerializer):
    food_name = serializers.CharField(source="food_item.name", read_only=True)

    class Meta:
        model = FoodEntry
        fields = [
            "id",
            "food_item",
            "food_name",
            "meal_type",
            "servings",
            "calories",
            "protein_g",
            "carbs_g",
            "fat_g",
            "logged_at",
        ]
        read_only_fields = ["calories", "protein_g", "carbs_g", "fat_g"]


class DailyEntrySerializer(serializers.ModelSerializer):
    food_entries = FoodEntrySerializer(many=True, read_only=True)
    total_calories = serializers.ReadOnlyField()
    total_protein = serializers.ReadOnlyField()
    total_carbs = serializers.ReadOnlyField()
    total_fat = serializers.ReadOnlyField()

    class Meta:
        model = DailyEntry
        fields = [
            "id",
            "date",
            "total_calories",
            "total_protein",
            "total_carbs",
            "total_fat",
            "food_entries",
        ]
