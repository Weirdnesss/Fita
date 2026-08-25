from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import DailyEntry, FoodEntry, FoodItem, NutritionProfile
from .serializers import (
    DailyEntrySerializer,
    FoodEntrySerializer,
    FoodItemSerializer,
    NutritionProfileSerializer,
)


class FoodSearchView(generics.ListAPIView):
    """
    GET /nutrition/foods/search/?q=adobo
    Searches the local FoodItem database -- instant, no external API,
    no rate limits. Falls back to listing everything if no query given
    (useful for browsing by category on the frontend).
    """

    serializer_class = FoodItemSerializer

    def get_queryset(self):
        q = self.request.query_params.get("q", "").strip()
        qs = FoodItem.objects.all()
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(local_name__icontains=q))
        category = self.request.query_params.get("category")
        if category:
            qs = qs.filter(category=category)
        return qs[:25]


class NutritionProfileView(generics.RetrieveUpdateAPIView):
    """GET/PATCH /nutrition/profile/  -- daily macro goals."""

    serializer_class = NutritionProfileSerializer

    def get_object(self):
        profile, _ = NutritionProfile.objects.get_or_create(user=self.request.user)
        return profile


class DailyEntryView(APIView):
    """
    GET /nutrition/daily/?date=2026-08-22  -- today's log if no date given.
    Returns the day's totals and every food entry, matching the
    Nutrition dashboard's per-meal breakdown.
    """

    def get(self, request):
        date_str = request.query_params.get("date")
        date = timezone.datetime.strptime(date_str, "%Y-%m-%d").date() if date_str else timezone.localdate()

        nutrition_profile, _ = NutritionProfile.objects.get_or_create(user=request.user)
        daily_entry, _ = DailyEntry.objects.get_or_create(
            nutrition_profile=nutrition_profile, date=date
        )
        return Response(DailyEntrySerializer(daily_entry).data)


class FoodEntryCreateView(APIView):
    """
    POST /nutrition/entries/
    Body: {"food_item": <id>, "meal_type": "breakfast", "servings": 1.5, "date": "2026-08-22"}
    The "Add Food" button on the Search Food -> Food Details screen.
    """

    def post(self, request):
        food_item_id = request.data.get("food_item")
        meal_type = request.data.get("meal_type")
        servings = request.data.get("servings", 1.0)
        date_str = request.data.get("date")

        if not food_item_id or not meal_type:
            return Response(
                {"error": "food_item and meal_type are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        food_item = get_object_or_404(FoodItem, id=food_item_id)
        date = (
            timezone.datetime.strptime(date_str, "%Y-%m-%d").date()
            if date_str
            else timezone.localdate()
        )

        nutrition_profile, _ = NutritionProfile.objects.get_or_create(user=request.user)
        daily_entry, _ = DailyEntry.objects.get_or_create(
            nutrition_profile=nutrition_profile, date=date
        )

        entry = FoodEntry.objects.create(
            daily_entry=daily_entry,
            food_item=food_item,
            meal_type=meal_type,
            servings=servings,
        )
        return Response(FoodEntrySerializer(entry).data, status=status.HTTP_201_CREATED)


class FoodEntryDeleteView(generics.DestroyAPIView):
    """DELETE /nutrition/entries/<id>/"""

    serializer_class = FoodEntrySerializer

    def get_queryset(self):
        return FoodEntry.objects.filter(
            daily_entry__nutrition_profile__user=self.request.user
        )
