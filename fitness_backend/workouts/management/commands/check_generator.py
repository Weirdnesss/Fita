"""
Shows why the workout generator does (or doesn't) pick exercises for a
category, using the generator's own rules -- nothing is changed or saved.

Usage (from the backend folder, where manage.py is):
  python manage.py check_generator                       # looks at "Back"
  python manage.py check_generator --category Chest
  python manage.py check_generator --email you@example.com   # also checks that account's profile
"""

from collections import Counter

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from workouts.models import WgerExercise
from workouts.services import workout_generator as g


def why_rejected(ex, category, location):
    """None if the exercise would be picked, otherwise the first rule that rejects it."""
    staples = g.COMMON_EXERCISE_KEYWORDS.get(category, [])
    if not staples:
        return f'no "staple" keywords are listed for {category}'
    if not g._name_has_keyword(ex.name, staples):
        return "name matches none of the staple keywords"
    if g._name_has_keyword(ex.name, g.BEGINNER_EXCLUDE_KEYWORDS):
        return "name hits the beginner-exclude list"
    equipment = (ex.equipment_name or "").lower()
    if "barbell" in equipment:
        return "uses a barbell"
    if location == g.WorkoutLocation.HOME and not any(h in equipment for h in g.HOME_EQUIPMENT):
        return "needs gym equipment (home workouts only)"
    return None


class Command(BaseCommand):
    help = "Explain which exercises the workout generator accepts or rejects for a category"

    def add_arguments(self, parser):
        parser.add_argument("--category", default="Back")
        parser.add_argument("--email", default=None, help="Also check this account's profile")

    def handle(self, *args, **options):
        category = options["category"]
        out = self.stdout.write

        total = WgerExercise.objects.count()
        out(f"Exercises in the cache: {total}")
        counts = Counter(WgerExercise.objects.values_list("category_name", flat=True))
        out("Categories in the cache: " + ", ".join(f"{c or '(blank)'}={n}" for c, n in sorted(counts.items())))
        out("")

        location = g.WorkoutLocation.GYM
        email = options["email"]
        if email:
            user = get_user_model().objects.filter(email__iexact=email).first()
            if user is None:
                out(self.style.ERROR(f"No account with email {email}"))
            else:
                profile, frequency, location, goal = g._profile_params(user)
                out(f"Account profile: frequency={frequency}, location={location}, goal={goal}")
                conditions = profile.medical_conditions if profile else ""
                out(f'medical_conditions: "{conditions}"')
                keywords = g._condition_keywords(conditions)
                excluded = sorted({c for k in keywords for c in g.CONDITION_EXCLUDED_CATEGORIES.get(k, [])})
                out(f"Matched condition keywords: {keywords or 'none'}  ->  categories dropped: {excluded or 'none'}")
                if category in excluded:
                    out(self.style.WARNING(f"  {category} is dropped for this account because of medical_conditions."))
                out("")

        rows = list(WgerExercise.objects.filter(category_name__iexact=category).order_by("name"))
        out(f"{category}: {len(rows)} exercises in the cache")
        passed = 0
        for ex in rows:
            reason = why_rejected(ex, category, location)
            if reason is None:
                passed += 1
                out(self.style.SUCCESS(f"  PICKABLE  {ex.name}  [{ex.equipment_name or 'no equipment'}]"))
            else:
                out(f"  rejected  {ex.name}  [{ex.equipment_name or 'no equipment'}]  -- {reason}")
        out("")
        out(f"{passed} of {len(rows)} {category} exercises can be picked ({location} workouts).")
