from django.db import transaction
from django.db.models import Case, IntegerField, Q, Sum, Value, When
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import Profile

from .models import DailyEntry, FoodEntry, FoodItem, MealType, NutritionProfile
from .serializers import (
    CustomFoodSerializer,
    DailyEntrySerializer,
    FoodEntrySerializer,
    FoodItemSerializer,
    NutritionProfileSerializer,
)
from .services.food_suggester import build_suggestions
from .services.meal_builder import MIN_PLATE_CALORIES, build_meal_suggestions
from .services.goal_calculator import REQUIRED_FIELDS, calculate_goals, missing_profile_fields
from .services.suggestion_llm import SuggestionExplainer

import logging

logger = logging.getLogger(__name__)

# How far back a food entry can be logged. Kept intentionally short --
# fixing yesterday's forgotten lunch is normal, but logging something
# from weeks ago is usually either low-confidence guessing or an attempt
# to pad historical totals, neither of which should be encouraged.
MAX_BACKDATE_DAYS = 7


def get_or_create_nutrition_profile(user):
    """
    Like NutritionProfile.objects.get_or_create(user=user), except on first
    creation it tries to seed personalized goals (Mifflin-St Jeor, via the
    same calculate_goals() used by the manual "Calculate" button) from the
    user's accounts.Profile instead of leaving the hardcoded generic
    defaults (2000 kcal / 100p / 250c / 65f) in place.

    Falls back to those defaults if the accounts.Profile is missing or
    incomplete (e.g. this is ever called for a user who skipped/exited the
    signup wizard partway through) -- this should never raise on account of
    incomplete profile data.
    """
    nutrition_profile, created = NutritionProfile.objects.get_or_create(user=user)
    if created:
        try:
            accounts_profile = user.profile
        except Profile.DoesNotExist:
            accounts_profile = None

        if accounts_profile and not missing_profile_fields(accounts_profile):
            result = calculate_goals(accounts_profile)
            nutrition_profile.daily_calories_goal = result.calories
            nutrition_profile.daily_protein_goal = result.protein_g
            nutrition_profile.daily_carbs_goal = result.carbs_g
            nutrition_profile.daily_fat_goal = result.fat_g
            nutrition_profile.save()

    return nutrition_profile, created

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


def visible_foods(user):
    """Foods this user may see and log: the shared database plus their own custom foods."""
    return FoodItem.objects.filter(Q(created_by__isnull=True) | Q(created_by=user))


def _parse_log_date(date_str):
    """
    Returns (date, error_response). Blank means today. Enforces the same
    rule everywhere food is logged: not in the future, not older than
    MAX_BACKDATE_DAYS.
    """
    today = timezone.localdate()
    if date_str:
        try:
            date = timezone.datetime.strptime(date_str, "%Y-%m-%d").date()
        except (TypeError, ValueError):
            return None, Response(
                {"error": "date must be in YYYY-MM-DD format"}, status=status.HTTP_400_BAD_REQUEST
            )
    else:
        date = today

    if date > today:
        return None, Response(
            {"error": "Can't log food for a future date."}, status=status.HTTP_400_BAD_REQUEST
        )
    oldest_allowed = today - timezone.timedelta(days=MAX_BACKDATE_DAYS)
    if date < oldest_allowed:
        return None, Response(
            {
                "error": f"Food can only be logged for the last {MAX_BACKDATE_DAYS} days.",
                "oldest_allowed_date": oldest_allowed.isoformat(),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )
    return date, None


def _parse_suggestion_params(request, default_limit, max_limit, max_exclude=200):
    """
    Query params shared by the two suggestion endpoints. Returns
    (params_dict, error_response).
    """
    meal_type, error = _validate_meal_type(request.query_params.get("meal_type"))
    if error:
        return None, error

    date_str = request.query_params.get("date")
    if date_str:
        try:
            date = timezone.datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            return None, Response(
                {"error": "date must be in YYYY-MM-DD format"}, status=status.HTTP_400_BAD_REQUEST
            )
    else:
        date = timezone.localdate()

    try:
        limit = int(request.query_params.get("limit", default_limit))
    except (TypeError, ValueError):
        limit = default_limit
    limit = min(max(limit, 1), max_limit)

    # `exclude=12,40`: foods already shown, for a "show different ideas" request.
    exclude_ids = {
        int(part) for part in request.query_params.get("exclude", "").split(",") if part.strip().isdigit()
    }
    return {
        "meal_type": meal_type,
        "date": date,
        "limit": limit,
        "explain": request.query_params.get("explain", "true").lower() != "false",
        "exclude_ids": set(sorted(exclude_ids)[:max_exclude]),
    }, None


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
        # PhilFCT, USDA and Open Food Facts rows are shared; custom foods
        # are visible only to the user who created them.
        qs = FoodItem.objects.filter(
            Q(created_by__isnull=True) | Q(created_by=self.request.user)
        )
        # Every word must match somewhere, in any order -- so "chicken
        # breast" finds USDA's "Chicken, broilers or fryers, breast, ...".
        for token in q.split():
            qs = qs.filter(
                Q(name__icontains=token)
                | Q(local_name__icontains=token)
                | Q(search_text__icontains=token)
            )
        category = self.request.query_params.get("category")
        if category:
            qs = qs.filter(category=category)

        # Ranking: names that start with the query first, then the
        # Filipino source (PhilFCT) ahead of imported/US data, then A-Z.
        source_rank = Case(
            When(created_by__isnull=False, then=Value(1)),
            When(source__startswith="PhilFCT", then=Value(0)),
            When(source__startswith="USDA", then=Value(2)),
            When(source__startswith="Open Food Facts", then=Value(3)),
            default=Value(4),
            output_field=IntegerField(),
        )
        match_rank = (
            Case(
                When(name__istartswith=q, then=Value(0)),
                default=Value(1),
                output_field=IntegerField(),
            )
            if q
            else Value(0, output_field=IntegerField())
        )
        return qs.annotate(_match_rank=match_rank, _source_rank=source_rank).order_by(
            "_match_rank", "_source_rank", "name"
        )

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


class CustomFoodCreateView(generics.CreateAPIView):
    """
    POST /nutrition/foods/custom/
    Body: {"name": "Lucky Me Pancit Canton", "category": "snacks",
           "serving_description": "1 pack (60 g)", "serving_size_g": 60,
           "calories": 280, "protein_g": 6, "carbs_g": 40, "fat_g": 10}
    Adds a private food (visible only to this user) so a missing item never
    blocks logging. Returned with the same shape as the search results.
    """

    serializer_class = CustomFoodSerializer

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user, source="User-submitted")

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return Response(FoodItemSerializer(serializer.instance).data, status=status.HTTP_201_CREATED)


class CustomFoodDetailView(generics.GenericAPIView):
    """
    PATCH/DELETE /nutrition/foods/custom/<id>/ -- own foods only.
    Editing is safe for history: logged entries snapshot their macros.
    Deleting a food that's already been logged is refused (409) since
    FoodEntry protects its food_item.
    """

    serializer_class = CustomFoodSerializer

    def get_queryset(self):
        return FoodItem.objects.filter(created_by=self.request.user)

    def patch(self, request, *args, **kwargs):
        food = get_object_or_404(self.get_queryset(), pk=kwargs["pk"])
        serializer = self.get_serializer(food, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(FoodItemSerializer(food).data)

    def delete(self, request, *args, **kwargs):
        food = get_object_or_404(self.get_queryset(), pk=kwargs["pk"])
        if FoodEntry.objects.filter(food_item=food).exists():
            return Response(
                {"error": "This food is in your log, so it can't be deleted. Edit it instead."},
                status=status.HTTP_409_CONFLICT,
            )
        food.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class FoodSuggestionsView(APIView):
    """
    GET /nutrition/suggestions/?meal_type=lunch&date=2026-10-19&limit=4&explain=true&exclude=12,40

    What could the user eat for this meal, given what's left of today's
    goals? Candidates and portions come from the database by rule; the LLM
    (when `explain` isn't false and it's reachable) only picks among them
    and words the reason. Any LLM failure silently falls back to the
    rule-based picks, with `reason_source` telling the client which it got.

    Each suggestion carries the food (same shape as search results), a
    suggested `servings` + `amount_label`, and the resulting macros, so the
    client can show a card and log it with the existing POST
    /nutrition/entries/ ({food_item, meal_type, servings, date}).
    """

    DEFAULT_LIMIT = 4
    MAX_LIMIT = 8
    MAX_EXCLUDE = 200  # ids honoured per request; the rest are ignored

    def get(self, request):
        params, error = _parse_suggestion_params(request, self.DEFAULT_LIMIT, self.MAX_LIMIT, self.MAX_EXCLUDE)
        if error:
            return error
        meal_type, date, limit = params["meal_type"], params["date"], params["limit"]
        explain, exclude_ids = params["explain"], params["exclude_ids"]

        nutrition_profile, _ = get_or_create_nutrition_profile(request.user)
        # Give the LLM a wider pool than we'll show, so it can pick for variety.
        remaining, candidates = build_suggestions(
            request.user, nutrition_profile, meal_type, date, limit=limit * 3, exclude_ids=exclude_ids
        )

        remaining_data = {
            "calories": round(remaining.calories, 1),
            "protein_g": round(remaining.protein_g, 1),
            "carbs_g": round(remaining.carbs_g, 1),
            "fat_g": round(remaining.fat_g, 1),
        }
        if not candidates:
            return Response(
                {
                    "meal_type": meal_type,
                    "date": date.isoformat(),
                    "remaining": remaining_data,
                    "suggestions": [],
                    "message": (
                        "You've almost reached today's calorie goal, so there's nothing to add."
                        if remaining.calories < 80
                        else "That's all the ideas for now."
                        if exclude_ids
                        else "No matching foods found for this meal yet."
                    ),
                }
            )

        chosen = [(c, c.reason, "rule") for c in candidates[:limit]]
        if explain:
            try:
                picks = SuggestionExplainer().pick_and_explain(meal_type, remaining, candidates, limit)
                if picks:
                    chosen = [(c, reason, "ai") for c, reason in picks]
            except Exception:
                # Missing key, rate limit, network error, SDK error: all
                # mean the same thing here -- use the rule-based picks.
                logger.warning("Suggestion LLM unavailable; using rule-based picks", exc_info=True)

        return Response(
            {
                "meal_type": meal_type,
                "date": date.isoformat(),
                "remaining": remaining_data,
                "suggestions": [
                    {
                        "food": FoodItemSerializer(c.food).data,
                        "servings": c.servings,
                        "amount_label": c.amount_label,
                        "calories": c.calories,
                        "protein_g": c.protein_g,
                        "carbs_g": c.carbs_g,
                        "fat_g": c.fat_g,
                        "reason": reason,
                        "reason_source": source,
                    }
                    for c, reason, source in chosen
                ],
            }
        )


class MealSuggestionsView(APIView):
    """
    GET /nutrition/suggestions/meals/?meal_type=lunch&date=2026-10-19&limit=3&explain=true&exclude=12,40

    Whole-plate ideas: a protein dish + a carb + a vegetable or fruit whose
    portions are worked out to fit what's left of today's goals. Same split
    as /suggestions/: foods, portions and numbers come from the database by
    rule; the LLM only picks among the plates and words the reason, and any
    failure falls back to rule-based reasons (`reason_source`).

    Each meal has `items` (food, role, servings, amount_label, macros) and
    `totals`. Log a whole plate in one go with POST /nutrition/entries/bulk/.
    `exclude` = food ids already shown; plates with one of them as their main
    (protein) item are skipped.
    """

    DEFAULT_LIMIT = 3
    MAX_LIMIT = 6

    def get(self, request):
        params, error = _parse_suggestion_params(request, self.DEFAULT_LIMIT, self.MAX_LIMIT)
        if error:
            return error
        meal_type, date, limit = params["meal_type"], params["date"], params["limit"]
        explain, exclude_ids = params["explain"], params["exclude_ids"]

        nutrition_profile, _ = get_or_create_nutrition_profile(request.user)
        # A wider pool than we show, so the LLM can pick for variety.
        remaining, plates = build_meal_suggestions(
            request.user, nutrition_profile, meal_type, date, limit=limit * 2, exclude_ids=exclude_ids
        )

        remaining_data = {
            "calories": round(remaining.calories, 1),
            "protein_g": round(remaining.protein_g, 1),
            "carbs_g": round(remaining.carbs_g, 1),
            "fat_g": round(remaining.fat_g, 1),
        }
        base = {"meal_type": meal_type, "date": date.isoformat(), "remaining": remaining_data}
        if not plates:
            if remaining.calories < MIN_PLATE_CALORIES:
                message = "There aren't enough calories left today for a full meal. Try single foods instead."
            elif exclude_ids:
                message = "That's all the meal ideas for now."
            else:
                message = "Couldn't put together a meal from the foods available. Try single foods instead."
            return Response({**base, "meals": [], "message": message})

        chosen = [(p, p.reason, "rule") for p in plates[:limit]]
        if explain:
            try:
                picks = SuggestionExplainer().pick_meals(meal_type, remaining, plates, limit)
                if picks:
                    chosen = [(p, reason, "ai") for p, reason in picks]
            except Exception:
                logger.warning("Meal suggestion LLM unavailable; using rule-based picks", exc_info=True)

        return Response(
            {
                **base,
                "meals": [
                    {
                        "items": [
                            {
                                "food": FoodItemSerializer(item.food).data,
                                "role": item.role,
                                "servings": item.servings,
                                "amount_label": item.amount_label,
                                "calories": item.calories,
                                "protein_g": item.protein_g,
                                "carbs_g": item.carbs_g,
                                "fat_g": item.fat_g,
                            }
                            for item in plate.items
                        ],
                        "totals": {
                            "calories": plate.calories,
                            "protein_g": plate.protein_g,
                            "carbs_g": plate.carbs_g,
                            "fat_g": plate.fat_g,
                        },
                        "reason": reason,
                        "reason_source": source,
                    }
                    for plate, reason, source in chosen
                ],
            }
        )


class NutritionProfileView(generics.RetrieveUpdateAPIView):
    """GET/PATCH /nutrition/profile/  -- daily macro goals."""

    serializer_class = NutritionProfileSerializer

    def get_object(self):
        profile, _ = get_or_create_nutrition_profile(self.request.user)
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

        nutrition_profile, _ = get_or_create_nutrition_profile(request.user)
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

class LoggedDatesView(APIView):
    """
    GET /nutrition/daily/dates/?month=2026-11
    The dates in that month that have at least one logged food. Feeds the
    dots in the Nutrition date picker. A DailyEntry row can outlive its
    foods (every entry deleted), so days are counted by food entries.
    """

    def get(self, request):
        month = request.query_params.get("month", "")
        try:
            year_str, month_str = month.split("-")
            year, mon = int(year_str), int(month_str)
            timezone.datetime(year, mon, 1)  # validates the range
        except (ValueError, TypeError):
            return Response({"detail": "month must look like 2026-11."}, status=status.HTTP_400_BAD_REQUEST)

        nutrition_profile, _ = get_or_create_nutrition_profile(request.user)
        dates = (
            DailyEntry.objects.filter(
                nutrition_profile=nutrition_profile,
                date__year=year,
                date__month=mon,
                food_entries__isnull=False,
            )
            .order_by("date")
            .values_list("date", flat=True)
            .distinct()
        )
        return Response({"dates": [d.isoformat() for d in dates]})


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

        nutrition_profile, _ = get_or_create_nutrition_profile(request.user)
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

        food_item = get_object_or_404(visible_foods(request.user), id=food_item_id)
        date, error = _parse_log_date(date_str)
        if error:
            return error

        nutrition_profile, _ = get_or_create_nutrition_profile(request.user)
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


class FoodEntryBulkCreateView(APIView):
    """
    POST /nutrition/entries/bulk/
    Body: {"meal_type": "lunch", "date": "2026-10-19",
           "items": [{"food_item": 12, "servings": 1.5}, {"food_item": 40, "servings": 2}]}
    Logs several foods to one meal at once -- the "Add all" button on a
    suggested plate. All-or-nothing: if any item is invalid, nothing is
    logged. Same rules as POST /entries/ (date window, servings limits, only
    foods the user can see).
    """

    MAX_ITEMS = 10

    def post(self, request):
        items = request.data.get("items")
        if not isinstance(items, list) or not items:
            return Response({"error": "items must be a non-empty list"}, status=status.HTTP_400_BAD_REQUEST)
        if len(items) > self.MAX_ITEMS:
            return Response(
                {"error": f"You can add at most {self.MAX_ITEMS} foods at once."}, status=status.HTTP_400_BAD_REQUEST
            )

        meal_type, error = _validate_meal_type(request.data.get("meal_type"))
        if error:
            return error
        date, error = _parse_log_date(request.data.get("date"))
        if error:
            return error

        visible = visible_foods(request.user)
        validated = []
        for item in items:
            if not isinstance(item, dict) or not item.get("food_item"):
                return Response(
                    {"error": "each item needs a food_item and servings"}, status=status.HTTP_400_BAD_REQUEST
                )
            servings, error = _validate_servings(item.get("servings", 1.0))
            if error:
                return error
            try:
                food_item = visible.filter(id=item["food_item"]).first()
            except (TypeError, ValueError):
                food_item = None
            if food_item is None:
                return Response({"error": "One of the foods wasn't found."}, status=status.HTTP_404_NOT_FOUND)
            validated.append((food_item, servings))

        nutrition_profile, _ = get_or_create_nutrition_profile(request.user)
        with transaction.atomic():
            daily_entry, _ = DailyEntry.objects.get_or_create(nutrition_profile=nutrition_profile, date=date)
            entries = [
                FoodEntry.objects.create(
                    daily_entry=daily_entry, food_item=food_item, meal_type=meal_type, servings=servings
                )
                for food_item, servings in validated
            ]
        return Response(FoodEntrySerializer(entries, many=True).data, status=status.HTTP_201_CREATED)


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
            entry.food_item = get_object_or_404(visible_foods(request.user), id=request.data["food_item"])

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