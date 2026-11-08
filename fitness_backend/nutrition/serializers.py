from rest_framework import serializers

from .models import DailyEntry, FoodEntry, FoodItem, NutritionProfile


SOURCE_LABELS = {
    "philfct": "PhilFCT",
    "usda": "USDA",
    "openfoodfacts": "Open Food Facts",
    "user": "My food",
    "estimated": "Estimated",
}


class FoodItemSerializer(serializers.ModelSerializer):
    is_verified = serializers.SerializerMethodField()
    source_type = serializers.ReadOnlyField()
    source_label = serializers.SerializerMethodField()
    is_custom = serializers.SerializerMethodField()

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
            "source_type",
            "source_label",
            "is_custom",
            "is_verified",
        ]

    def get_is_verified(self, obj):
        """True for real PhilFCT-sourced rows only (kept for existing clients).
        New UI should use source_type / source_label instead, since USDA and
        Open Food Facts rows are real data too, just not Filipino-sourced."""
        return obj.source.startswith("PhilFCT")

    def get_source_label(self, obj):
        return SOURCE_LABELS[obj.source_type]

    def get_is_custom(self, obj):
        return obj.created_by_id is not None


class CustomFoodSerializer(serializers.ModelSerializer):
    """
    Create/edit a user's own food, from a nutrition label or a home recipe.
    Everything is per `serving_description` (e.g. '1 pack (60 g)'), matching
    how FoodItem rows are stored. Bounds are sanity guards against typos,
    not nutrition advice.
    """

    # If the macros imply a calorie figure this far from the stated one,
    # the entry is almost certainly a typo (a misplaced decimal, label
    # values for the wrong serving size). 40% leaves room for fiber,
    # sugar alcohols and rounding on real labels.
    MAX_CALORIE_MISMATCH = 0.40
    MIN_CALORIES_TO_CHECK = 50

    name = serializers.CharField(max_length=200)
    serving_description = serializers.CharField(max_length=100)
    serving_size_g = serializers.FloatField(min_value=1, max_value=2000)
    calories = serializers.FloatField(min_value=0, max_value=3000)
    protein_g = serializers.FloatField(min_value=0, max_value=500)
    carbs_g = serializers.FloatField(min_value=0, max_value=500)
    fat_g = serializers.FloatField(min_value=0, max_value=500)
    fiber_g = serializers.FloatField(min_value=0, max_value=500, required=False, allow_null=True)
    sodium_mg = serializers.FloatField(min_value=0, max_value=50000, required=False, allow_null=True)

    class Meta:
        model = FoodItem
        fields = [
            "id",
            "name",
            "category",
            "serving_description",
            "serving_size_g",
            "calories",
            "protein_g",
            "carbs_g",
            "fat_g",
            "fiber_g",
            "sodium_mg",
        ]

    def validate(self, attrs):
        # On PATCH, validate against the merged result, not just the sent fields.
        merged = {
            f: attrs.get(f, getattr(self.instance, f, None))
            for f in ("calories", "protein_g", "carbs_g", "fat_g")
        }
        calories = merged["calories"]
        if calories is not None and calories >= self.MIN_CALORIES_TO_CHECK:
            implied = (
                (merged["protein_g"] or 0) * 4
                + (merged["carbs_g"] or 0) * 4
                + (merged["fat_g"] or 0) * 9
            )
            if abs(implied - calories) / calories > self.MAX_CALORIE_MISMATCH:
                raise serializers.ValidationError(
                    "Calories don't match the protein/carbs/fat you entered. "
                    "Double-check the serving size and the numbers from the label."
                )
        return attrs


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
            "auto_recalculate_goals",
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