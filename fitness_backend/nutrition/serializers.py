from rest_framework import serializers

from .models import DailyEntry, FoodEntry, FoodItem, NutritionProfile


class FoodItemSerializer(serializers.ModelSerializer):
    is_verified = serializers.SerializerMethodField()

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
            "is_verified",
        ]

    def get_is_verified(self, obj):
        """True for real PhilFCT-sourced rows, False for hand-estimated dishes."""
        return obj.source.startswith("PhilFCT")


class NutritionProfileSerializer(serializers.ModelSerializer):
    # Bounds here are basic data-sanity guards, not nutrition advice --
    # they exist to catch zero/negative/fat-fingered values (a calories
    # goal of 0 breaks the dashboard's percentage math via division by
    # zero) rather than to police what a "safe" goal looks like. The more
    # nuanced safety-floor logic lives in goal_calculator.py, which only
    # applies to the auto-calculate suggestion, not a manual override.
    daily_calories_goal = serializers.FloatField(min_value=500, max_value=10000)
    daily_protein_goal = serializers.FloatField(min_value=10, max_value=1000)
    daily_carbs_goal = serializers.FloatField(min_value=10, max_value=1000)
    daily_fat_goal = serializers.FloatField(min_value=10, max_value=1000)

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
    serving_description = serializers.CharField(source="food_item.serving_description", read_only=True)
    serving_size_g = serializers.FloatField(source="food_item.serving_size_g", read_only=True)

    class Meta:
        model = FoodEntry
        fields = [
            "id",
            "food_item",
            "food_name",
            "meal_type",
            "servings",
            "serving_description",
            "serving_size_g",
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
