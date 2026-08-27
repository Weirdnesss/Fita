"""
Pulls together everything the Fitness Assistant needs to know about a
user -- profile, recent workouts, recent nutrition -- into one plain-text
summary that gets injected into the LLM's system prompt. This is the
"contextual awareness" layer, built against our own models.
"""

from django.utils import timezone

from nutrition.models import DailyEntry, NutritionProfile
from workouts.models import TemplateHistory


class DataCollectionService:
    def __init__(self, user):
        self.user = user

    def get_profile_summary(self):
        profile = getattr(self.user, "profile", None)
        if not profile:
            return "No profile data available."

        lines = []
        if profile.gender:
            lines.append(f"Gender: {profile.get_gender_display()}")
        if profile.activity_level:
            lines.append(f"Activity level: {profile.get_activity_level_display()}")
        if profile.current_weight_kg:
            lines.append(f"Current weight: {profile.current_weight_kg} kg")
        if profile.goal_weight_kg:
            lines.append(f"Goal weight: {profile.goal_weight_kg} kg")
        if profile.height_cm:
            lines.append(f"Height: {profile.height_cm} cm")
        if profile.bmi:
            lines.append(f"BMI: {profile.bmi}")
        if profile.primary_goal:
            lines.append(f"Primary goal: {profile.get_primary_goal_display()}")
        if profile.workout_frequency:
            lines.append(f"Target workout frequency: {profile.workout_frequency} days/week")
        if profile.workout_location:
            lines.append(f"Workout location: {profile.get_workout_location_display()}")
        if profile.medical_conditions:
            lines.append(f"Medical conditions / injuries: {profile.medical_conditions}")
        if profile.food_allergies:
            lines.append(f"Food allergies/restrictions: {profile.food_allergies}")
        return "\n".join(lines) if lines else "No profile data available."

    def get_recent_workouts_summary(self, limit=5):
        history = TemplateHistory.objects.filter(user=self.user)[:limit]
        if not history.exists():
            return "No workout history logged yet."

        lines = [f"Last {history.count()} workout session(s):"]
        for session in history:
            lines.append(
                f"- {session.completed_at:%Y-%m-%d} \"{session.template_title}\": "
                f"{session.total_exercises} exercises, {session.total_sets} sets, "
                f"{session.duration_minutes} min"
            )
            if session.note:
                lines.append(f"  Note: {session.note}")
        return "\n".join(lines)

    def get_recent_nutrition_summary(self, days=7):
        nutrition_profile = getattr(self.user, "nutrition_profile", None)
        if not nutrition_profile:
            return "No nutrition data logged yet."

        entries = DailyEntry.objects.filter(nutrition_profile=nutrition_profile)[:days]
        if not entries.exists():
            return "No nutrition data logged yet."

        goal_cal = nutrition_profile.daily_calories_goal
        goal_protein = nutrition_profile.daily_protein_goal
        lines = [
            f"Daily goals: {goal_cal} kcal, {goal_protein}g protein, "
            f"{nutrition_profile.daily_carbs_goal}g carbs, {nutrition_profile.daily_fat_goal}g fat"
        ]
        lines.append(f"Last {entries.count()} tracked day(s):")
        for entry in entries:
            lines.append(
                f"- {entry.date}: {entry.total_calories:.0f} kcal "
                f"({entry.total_protein:.0f}g protein, {entry.total_carbs:.0f}g carbs, "
                f"{entry.total_fat:.0f}g fat)"
            )
        return "\n".join(lines)

    def get_full_context(self):
        return (
            "=== USER PROFILE ===\n"
            f"{self.get_profile_summary()}\n\n"
            "=== RECENT WORKOUTS ===\n"
            f"{self.get_recent_workouts_summary()}\n\n"
            "=== RECENT NUTRITION ===\n"
            f"{self.get_recent_nutrition_summary()}"
        )

    # -- Structured, period-scoped data for the Progress Report module --
    # (separate from the "recent N" methods above, which serve the chat
    # assistant's rolling context)

    def get_structured_nutrition_data(self, period_start, period_end):
        nutrition_profile = getattr(self.user, "nutrition_profile", None)
        if not nutrition_profile:
            return {"has_data": False, "message": "No nutrition profile set up"}

        entries = DailyEntry.objects.filter(
            nutrition_profile=nutrition_profile,
            date__gte=period_start,
            date__lte=period_end,
        )
        if not entries.exists():
            return {"has_data": False, "message": "No nutrition data logged in this period"}

        total_days = entries.count()
        avg_calories = sum(e.total_calories for e in entries) / total_days
        avg_protein = sum(e.total_protein for e in entries) / total_days
        avg_carbs = sum(e.total_carbs for e in entries) / total_days
        avg_fat = sum(e.total_fat for e in entries) / total_days

        goals = {
            "calories": nutrition_profile.daily_calories_goal,
            "protein": nutrition_profile.daily_protein_goal,
            "carbs": nutrition_profile.daily_carbs_goal,
            "fat": nutrition_profile.daily_fat_goal,
        }

        def pct(actual, goal):
            return round(min((actual / goal) * 100, 100), 1) if goal else 0.0

        adherence = {
            "calories": pct(avg_calories, goals["calories"]),
            "protein": pct(avg_protein, goals["protein"]),
            "carbs": pct(avg_carbs, goals["carbs"]),
            "fat": pct(avg_fat, goals["fat"]),
        }
        adherence["overall"] = round(
            sum(adherence.values()) / len(adherence), 1
        )

        return {
            "has_data": True,
            "total_days_tracked": total_days,
            "period_days": (period_end - period_start).days + 1,
            "averages": {
                "calories": round(avg_calories, 1),
                "protein": round(avg_protein, 1),
                "carbs": round(avg_carbs, 1),
                "fat": round(avg_fat, 1),
            },
            "goals": goals,
            "adherence": adherence,
        }

    def get_structured_workout_data(self, period_start, period_end):
        from django.utils import timezone as tz

        start_dt = tz.make_aware(tz.datetime.combine(period_start, tz.datetime.min.time()))
        end_dt = tz.make_aware(tz.datetime.combine(period_end, tz.datetime.max.time()))

        history = TemplateHistory.objects.filter(
            user=self.user, completed_at__gte=start_dt, completed_at__lte=end_dt
        )
        if not history.exists():
            return {"has_data": False, "message": "No workouts logged in this period"}

        total_workouts = history.count()
        total_exercises = sum(h.total_exercises for h in history)
        total_sets = sum(h.total_sets for h in history)
        total_minutes = sum(h.duration_minutes for h in history)
        avg_duration = round(total_minutes / total_workouts, 1) if total_workouts else 0

        period_days = (period_end - period_start).days + 1
        workouts_per_week = round(total_workouts / (period_days / 7), 1) if period_days else 0

        unique_exercises = set()
        for h in history:
            for pe in h.performed_exercises.all():
                unique_exercises.add(pe.exercise_name)

        # Notes are kept separate from the numeric fields above: the
        # RuleBasedAnalyzer only reads the numeric/aggregate fields (it
        # has no rule that understands free text), but this whole dict
        # is also handed to the LLM narrator as JSON context, and the
        # narrator can use notes the same way the coach chat does.
        workout_notes = [
            f"{h.completed_at:%Y-%m-%d}: {h.note}" for h in history if h.note
        ]

        return {
            "has_data": True,
            "total_workouts": total_workouts,
            "total_exercises_performed": total_exercises,
            "total_sets_performed": total_sets,
            "total_workout_minutes": round(total_minutes, 1),
            "average_workout_duration": avg_duration,
            "workouts_per_week": workouts_per_week,
            "exercise_variety": len(unique_exercises),
            "period_days": period_days,
            "workout_notes": workout_notes,
        }