from django.contrib import admin

from .models import DailyEntry, FoodEntry, FoodItem, NutritionProfile

admin.site.register(FoodItem)
admin.site.register(NutritionProfile)
admin.site.register(DailyEntry)
admin.site.register(FoodEntry)
