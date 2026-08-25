from django.conf import settings
from django.db import models


class FoodCategory(models.TextChoices):
    RICE_GRAINS = "rice_grains", "Rice & Grains"
    VIANDS_MEAT = "viands_meat", "Viands - Meat & Poultry"
    VIANDS_FISH = "viands_fish", "Viands - Fish & Seafood"
    VEGETABLES = "vegetables", "Vegetables"
    FRUITS = "fruits", "Fruits"
    SOUPS = "soups", "Soups & Stews"
    SNACKS = "snacks", "Snacks & Merienda"
    DESSERTS = "desserts", "Desserts & Sweets"
    BEVERAGES = "beverages", "Beverages"
    CONDIMENTS = "condiments", "Condiments & Sauces"
    OTHER = "other", "Other"


class FoodItem(models.Model):
    """
    A local Filipino food database, structured after PhilFCT's fields
    (food name, edible-portion serving, energy + macros per serving).

    Values here should be sourced/cross-checked against the PhilFCT
    Online Database (https://i.fnri.dost.gov.ph/fct/library) or an
    FNRI data request, and cited as such in the thesis methodology --
    seed data is a starting point, not a substitute for verification.
    """

    name = models.CharField(max_length=200)
    local_name = models.CharField(
        max_length=200, blank=True, help_text="Filipino/regional name if different"
    )
    category = models.CharField(max_length=20, choices=FoodCategory.choices)

    serving_description = models.CharField(
        max_length=100, help_text="e.g. '1 cup cooked', '1 piece (medium)', '100g'"
    )
    serving_size_g = models.FloatField(help_text="Edible portion weight in grams")

    calories = models.FloatField(help_text="kcal per serving_description")
    protein_g = models.FloatField(default=0)
    carbs_g = models.FloatField(default=0)
    fat_g = models.FloatField(default=0)
    fiber_g = models.FloatField(null=True, blank=True)
    sodium_mg = models.FloatField(null=True, blank=True)

    source = models.CharField(
        max_length=100,
        default="PhilFCT (cross-referenced)",
        help_text="Data provenance, e.g. 'PhilFCT 2019', 'FNRI FOI request', 'estimated'",
    )

    class Meta:
        ordering = ["name"]
        indexes = [models.Index(fields=["name"])]

    def __str__(self):
        return f"{self.name} ({self.serving_description})"


class NutritionProfile(models.Model):
    """Per-user daily macro goals, derived from Profile via BMR/TDEE."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="nutrition_profile"
    )
    daily_calories_goal = models.FloatField(default=2000)
    daily_protein_goal = models.FloatField(default=100)
    daily_carbs_goal = models.FloatField(default=250)
    daily_fat_goal = models.FloatField(default=65)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"NutritionProfile<{self.user.email}>"


class MealType(models.TextChoices):
    BREAKFAST = "breakfast", "Breakfast"
    LUNCH = "lunch", "Lunch"
    DINNER = "dinner", "Dinner"
    SNACK = "snack", "Snack"


class DailyEntry(models.Model):
    """All logged food for one user on one date."""

    nutrition_profile = models.ForeignKey(
        NutritionProfile, on_delete=models.CASCADE, related_name="daily_entries"
    )
    date = models.DateField()

    class Meta:
        unique_together = ["nutrition_profile", "date"]
        ordering = ["-date"]

    @property
    def total_calories(self):
        return sum(f.calories for f in self.food_entries.all())

    @property
    def total_protein(self):
        return sum(f.protein_g for f in self.food_entries.all())

    @property
    def total_carbs(self):
        return sum(f.carbs_g for f in self.food_entries.all())

    @property
    def total_fat(self):
        return sum(f.fat_g for f in self.food_entries.all())

    def __str__(self):
        return f"{self.nutrition_profile.user.email} - {self.date}"


class FoodEntry(models.Model):
    """One logged food item within a DailyEntry, at a chosen meal + quantity."""

    daily_entry = models.ForeignKey(
        DailyEntry, on_delete=models.CASCADE, related_name="food_entries"
    )
    food_item = models.ForeignKey(FoodItem, on_delete=models.PROTECT)
    meal_type = models.CharField(max_length=10, choices=MealType.choices)
    servings = models.FloatField(default=1.0)

    # Snapshot the macros at log time (scaled by servings) so edits to
    # FoodItem later don't silently rewrite historical logs.
    calories = models.FloatField()
    protein_g = models.FloatField()
    carbs_g = models.FloatField()
    fat_g = models.FloatField()

    logged_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.pk:
            self.calories = self.food_item.calories * self.servings
            self.protein_g = self.food_item.protein_g * self.servings
            self.carbs_g = self.food_item.carbs_g * self.servings
            self.fat_g = self.food_item.fat_g * self.servings
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.food_item.name} x{self.servings} ({self.meal_type})"
