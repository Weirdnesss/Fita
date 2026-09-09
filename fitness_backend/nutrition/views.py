from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db.models import Q, Sum

from accounts.models import Profile

from .models import DailyEntry, FoodEntry, FoodItem, MealType, NutritionProfile
from .serializers import (
    DailyEntrySerializer,
    FoodEntrySerializer,
    FoodItemSerializer,
    NutritionProfileSerializer,
)
from .services.goal_calculator import REQUIRED_FIELDS, calculate_goals, missing_profile_fields

# How far back a food entry can be logged. Kept intentionally short --
# fixing yesterday's forgotten lunch is normal, but logging something
# from weeks ago is usually either low-confidence guessing or an attempt
# to pad historical totals, neither of which should be encouraged.
MAX_BACKDATE_DAYS = 7

# Sanity ceiling on servings -- catches fat-fingered input (e.g. an extra
# zero) rather than any real intended amount. 50 servings of a 100g
# PhilFCT item is already 5kg of food in one entry, well past anything
# real.
MAX_SERVINGS = 50


def _validate_servings(raw_value):
    """
    Returns (servings: float, error_response: Response|None). On success,
    error_response is None -- check that before using servings.
    """
    try:
        servings = float(raw_value)
    except (TypeError, ValueError):
        return None, Response({"error": "servings must be a number"}, status=status.HTTP_400_BAD_REQUEST)
    if servings <= 0:
        return None, Response({"error": "servings must be greater than 0"}, status=status.HTTP_400_BAD_REQUEST)
    if servings > MAX_SERVINGS:
        return None, Response(
            {"error": f"servings can't exceed {MAX_SERVINGS}"}, status=status.HTTP_400_BAD_REQUEST
        )
    return servings, None


def _validate_meal_type(raw_value):
    """Returns (meal_type: str, error_response: Response|None)."""
    if raw_value not in MealType.values:
        return None, Response(
            {"error": f"meal_type must be one of {MealType.values}"}, status=status.HTTP_400_BAD_REQUEST
        )
    return raw_value, None


class FoodSearchView(generics.ListAPIView):
    """
    GET /nutrition/foods/search/?q=adobo&category=viands_meat&offset=40
    Searches the local FoodItem database -- instant, no external API,
    no rate limits. With no query, lists by category (or everything) so
    the frontend can support category browsing, not just text search.

    Paginated via `offset` (default 0), page size PAGE_SIZE. Response
    includes `count` (total matches) and `next_offset` (null once
    there's nothing more to load), so the frontend can drive a
    "Load More" button without guessing at page math.
    """

    serializer_class = FoodItemSerializer
    PAGE_SIZE = 40

    def get_queryset(self):
        q = self.request.query_params.get("q", "").strip()
        qs = FoodItem.objects.all()
        if q:
            qs = qs.filter(
                Q(name__icontains=q) | Q(local_name__icontains=q) | Q(search_text__icontains=q)
            )
        category = self.request.query_params.get("category")
        if category:
            qs = qs.filter(category=category)
        return qs

    def list(self, request, *args, **kwargs):
        qs = self.get_queryset()
        total = qs.count()

        try:
            offset = int(request.query_params.get("offset", 0))
        except (TypeError, ValueError):
            offset = 0
        offset = max(offset, 0)

        page = qs[offset : offset + self.PAGE_SIZE]
        serializer = self.get_serializer(page, many=True)
        next_offset = offset + self.PAGE_SIZE

        return Response({
            "count": total,
            "results": serializer.data,
            "next_offset": next_offset if next_offset < total else None,
        })


class NutritionProfileView(generics.RetrieveUpdateAPIView):
    """GET/PATCH /nutrition/profile/  -- daily macro goals."""

    serializer_class = NutritionProfileSerializer

    def get_object(self):
        profile, _ = NutritionProfile.objects.get_or_create(user=self.request.user)
        return profile


class SuggestedGoalsView(APIView):
    """
    GET /nutrition/goals/suggested/
    Calculates suggested daily calorie/macro goals from the user's
    accounts.Profile (weight, height, age, gender, activity level, goal)
    using the Mifflin-St Jeor BMR formula. Doesn't save anything -- the
    frontend shows the suggestion and lets the user apply it (PATCH
    /nutrition/profile/) or adjust it first.

    Returns 422 with a list of missing fields if weight/height/age/gender
    aren't set yet, so the frontend can prompt for just those.
    """

    def get(self, request):
        try:
            profile = request.user.profile
        except Profile.DoesNotExist:
            profile = None

        missing = missing_profile_fields(profile) if profile else list(REQUIRED_FIELDS)
        if missing:
            return Response(
                {"detail": "Missing profile data needed to calculate goals.", "missing_fields": missing},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        result = calculate_goals(profile)
        return Response(
            {
                "calories": result.calories,
                "protein_g": result.protein_g,
                "carbs_g": result.carbs_g,
                "fat_g": result.fat_g,
                "bmr": result.bmr,
                "tdee": result.tdee,
                "calorie_floor_applied": result.calorie_floor_applied,
                "assumptions": result.assumptions,
            }
        )


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
        daily_entry = DailyEntry.objects.filter(
            nutrition_profile=nutrition_profile, date=date
        ).first()
        if daily_entry is None:
            # Deliberately NOT get_or_create here -- viewing an empty day
            # used to permanently create a DailyEntry row for it, which
            # then got miscounted as a "tracked day" elsewhere (progress
            # report, coach context) even with zero food logged. A row is
            # only created once food is actually added, in
            # FoodEntryCreateView below. This response matches
            # DailyEntrySerializer's shape for a day with nothing in it.
            return Response(
                {
                    "id": None,
                    "date": date.isoformat(),
                    "total_calories": 0,
                    "total_protein": 0,
                    "total_carbs": 0,
                    "total_fat": 0,
                    "food_entries": [],
                }
            )
        return Response(DailyEntrySerializer(daily_entry).data)

class NutritionTrendsView(APIView):
    """
    GET /nutrition/trends/?period=week|month
    Aggregates daily totals over the trailing 7 (week) or 30 (month)
    days, plus a logging streak and per-macro averages -- feeds the
    Trends tab's bar chart and streak/averages cards.

    Averages are computed over days that actually have food logged,
    not every day in the period -- averaging in zero-calorie days the
    user simply didn't open the app on would understate real intake
    and isn't useful feedback.
    """

    PERIOD_DAYS = {"week": 7, "month": 30}

    def get(self, request):
        period = request.query_params.get("period", "week")
        num_days = self.PERIOD_DAYS.get(period)
        if num_days is None:
            return Response(
                {"error": f"period must be one of {list(self.PERIOD_DAYS)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        nutrition_profile, _ = NutritionProfile.objects.get_or_create(user=request.user)
        today = timezone.localdate()
        start_date = today - timezone.timedelta(days=num_days - 1)

        totals_by_date = {
            row["daily_entry__date"]: row
            for row in (
                FoodEntry.objects.filter(
                    daily_entry__nutrition_profile=nutrition_profile,
                    daily_entry__date__gte=start_date,
                    daily_entry__date__lte=today,
                )
                .values("daily_entry__date")
                .annotate(
                    calories=Sum("calories"),
                    protein_g=Sum("protein_g"),
                    carbs_g=Sum("carbs_g"),
                    fat_g=Sum("fat_g"),
                )
            )
        }

        days = []
        for i in range(num_days):
            d = start_date + timezone.timedelta(days=i)
            row = totals_by_date.get(d)
            days.append({
                "date": d.isoformat(),
                "calories": row["calories"] if row else 0,
                "protein_g": row["protein_g"] if row else 0,
                "carbs_g": row["carbs_g"] if row else 0,
                "fat_g": row["fat_g"] if row else 0,
                "logged": row is not None,
            })

        logged_days = [d for d in days if d["logged"]]
        days_logged = len(logged_days)

        def avg(field):
            return round(sum(d[field] for d in logged_days) / days_logged, 1) if days_logged else 0

        return Response({
            "period": period,
            "days": days,
            "days_logged": days_logged,
            "averages": {
                "calories": avg("calories"),
                "protein_g": avg("protein_g"),
                "carbs_g": avg("carbs_g"),
                "fat_g": avg("fat_g"),
            },
            "current_streak": self._current_streak(nutrition_profile, today),
        })

    def _current_streak(self, nutrition_profile, today):
        # Consecutive days with at least one food entry, walking backward
        # from today. If today has nothing logged yet, start counting
        # from yesterday instead -- today isn't "over" yet, so not having
        # logged breakfast by 9am shouldn't zero out an otherwise-intact
        # streak.
        logged_dates = set(
            DailyEntry.objects.filter(nutrition_profile=nutrition_profile, food_entries__isnull=False)
            .distinct()
            .values_list("date", flat=True)
        )
        cursor = today if today in logged_dates else today - timezone.timedelta(days=1)
        streak = 0
        while cursor in logged_dates:
            streak += 1
            cursor -= timezone.timedelta(days=1)
        return streak


class FoodEntryCreateView(APIView):
    """
    POST /nutrition/entries/
    Body: {"food_item": <id>, "meal_type": "breakfast", "servings": 1.5, "date": "2026-08-22"}
    The "Add Food" button on the Search Food -> Food Details screen.
    """

    def post(self, request):
        food_item_id = request.data.get("food_item")
        meal_type = request.data.get("meal_type")
        servings_raw = request.data.get("servings", 1.0)
        date_str = request.data.get("date")

        if not food_item_id or not meal_type:
            return Response(
                {"error": "food_item and meal_type are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        meal_type, error = _validate_meal_type(meal_type)
        if error:
            return error
        servings, error = _validate_servings(servings_raw)
        if error:
            return error

        food_item = get_object_or_404(FoodItem, id=food_item_id)
        if date_str:
            try:
                date = timezone.datetime.strptime(date_str, "%Y-%m-%d").date()
            except ValueError:
                return Response(
                    {"error": "date must be in YYYY-MM-DD format"}, status=status.HTTP_400_BAD_REQUEST
                )
        else:
            date = timezone.localdate()

        today = timezone.localdate()
        if date > today:
            return Response(
                {"error": "Can't log food for a future date."}, status=status.HTTP_400_BAD_REQUEST
            )
        oldest_allowed = today - timezone.timedelta(days=MAX_BACKDATE_DAYS)
        if date < oldest_allowed:
            return Response(
                {
                    "error": f"Food can only be logged for the last {MAX_BACKDATE_DAYS} days.",
                    "oldest_allowed_date": oldest_allowed.isoformat(),
                },
                status=status.HTTP_400_BAD_REQUEST,
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


class FoodEntryDetailView(generics.GenericAPIView):
    """
    PATCH /nutrition/entries/<id>/  -- edit servings and/or meal_type.
    DELETE /nutrition/entries/<id>/ -- remove entirely, no date restriction.

    Editing supports servings, meal_type, food_item (swap), and date
    (move to a different day). A food_item/date change moves the entry
    onto the correct DailyEntry and re-snapshots calories/macros against
    the new food_item and/or servings.

    Editing is subject to the same MAX_BACKDATE_DAYS window as creating
    a new entry: quietly inflating an old entry's servings has the same
    effect as backdating a fabricated one, so it's bound by the same
    rule. Deleting is deliberately NOT bound by it -- removing your own
    bad data isn't the same risk as fabricating good-looking data.
    """

    serializer_class = FoodEntrySerializer

    def get_queryset(self):
        return FoodEntry.objects.filter(daily_entry__nutrition_profile__user=self.request.user)

    def patch(self, request, *args, **kwargs):
        entry = get_object_or_404(self.get_queryset(), pk=kwargs["pk"])

        entry_date = entry.daily_entry.date
        oldest_allowed = timezone.localdate() - timezone.timedelta(days=MAX_BACKDATE_DAYS)
        if entry_date < oldest_allowed:
            return Response(
                {"error": f"Entries older than {MAX_BACKDATE_DAYS} days can't be edited, only removed."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if "meal_type" in request.data:
            meal_type, error = _validate_meal_type(request.data["meal_type"])
            if error:
                return error
            entry.meal_type = meal_type

        if "servings" in request.data:
            servings, error = _validate_servings(request.data["servings"])
            if error:
                return error
            entry.servings = servings

        if "food_item" in request.data:
            entry.food_item = get_object_or_404(FoodItem, id=request.data["food_item"])

        if "date" in request.data:
            try:
                new_date = timezone.datetime.strptime(request.data["date"], "%Y-%m-%d").date()
            except (TypeError, ValueError):
                return Response(
                    {"error": "date must be in YYYY-MM-DD format"}, status=status.HTTP_400_BAD_REQUEST
                )

            today = timezone.localdate()
            if new_date > today:
                return Response(
                    {"error": "Can't move a food entry to a future date."}, status=status.HTTP_400_BAD_REQUEST
                )
            if new_date < oldest_allowed:
                return Response(
                    {
                        "error": f"Food can only be logged for the last {MAX_BACKDATE_DAYS} days.",
                        "oldest_allowed_date": oldest_allowed.isoformat(),
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if new_date != entry_date:
                # Move the entry to a (possibly new) DailyEntry for the
                # target date, rather than mutating a date field on
                # FoodEntry directly -- DailyEntry is the actual grouping
                # unit everything else (totals, reports) reads from. An
                # old DailyEntry left with zero food_entries is harmless:
                # data_collection_service already only counts days with
                # actual food_entries as "tracked".
                new_daily_entry, _ = DailyEntry.objects.get_or_create(
                    nutrition_profile=entry.daily_entry.nutrition_profile, date=new_date
                )
                entry.daily_entry = new_daily_entry

        # Recompute the snapshot unconditionally -- food_item and/or
        # servings may have changed, and recomputing is cheap enough that
        # tracking exactly which fields changed isn't worth it.
        entry.calories = entry.food_item.calories * entry.servings
        entry.protein_g = entry.food_item.protein_g * entry.servings
        entry.carbs_g = entry.food_item.carbs_g * entry.servings
        entry.fat_g = entry.food_item.fat_g * entry.servings
        entry.save()

        return Response(FoodEntrySerializer(entry).data)

    def delete(self, request, *args, **kwargs):
        entry = get_object_or_404(self.get_queryset(), pk=kwargs["pk"])
        entry.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)