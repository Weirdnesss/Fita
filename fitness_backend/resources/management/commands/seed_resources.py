"""
Seeds a starter set of curated fitness/nutrition articles into the
Resource catalog (see resources/models.py docstring -- this is global,
read-only, curated content, populated the same way nutrition's
seed_foods.py populates FoodItem).

All entries below link to real articles from reputable, non-commercial
sources (NASM, ACE Fitness, Healthline, Harvard Health, Mayo Clinic,
CDC) so they're safe to cite directly in your thesis if needed. Titles
and URLs were checked at the time this command was written -- if a
link ever 404s, just fix or remove that row and re-run.

Run with: python manage.py seed_resources
"""

from django.core.management.base import BaseCommand

from resources.models import Resource, ResourceCategory

STARTER_RESOURCES = [
    # title, summary, category, url, source
    (
        "Functional Strength Training: Exercises Your Clients Will Actually Feel",
        "Beginner-friendly strength training built around the six foundational "
        "movement patterns: squat, hinge, lunge, push, pull, and carry.",
        ResourceCategory.WORKOUT,
        "https://www.nasm.org/resource-center/blog/training/functional-strength-training",
        "NASM",
    ),
    (
        "A Guide to At-Home Workouts for Beginners",
        "A bodyweight routine covering muscular fitness, cardio endurance, and "
        "core stability -- no equipment needed.",
        ResourceCategory.WORKOUT,
        "https://www.acefitness.org/resources/everyone/blog/7855/a-guide-to-at-home-workouts-for-beginners/",
        "ACE Fitness",
    ),
    (
        "ACE's Kick-Start Workout: A Week-by-Week 3-Month Exercise Program",
        "A 12-week program for people new to exercise, starting with walking and "
        "progressively increasing frequency, duration, and intensity.",
        ResourceCategory.WORKOUT,
        "https://www.acefitness.org/resources/everyone/blog/6594/ace-s-kick-start-workout-a-week-by-week-3-month-exercise-program/",
        "ACE Fitness",
    ),
    (
        "Protein Intake: How Much Protein Should You Eat per Day?",
        "Breaks down daily protein needs by body weight, activity level, and "
        "goals, and clears up the common gram-of-protein-vs-gram-of-food mix-up.",
        ResourceCategory.NUTRITION,
        "https://www.healthline.com/nutrition/how-much-protein-per-day",
        "Healthline",
    ),
    (
        "How Much Protein Do You Need Every Day?",
        "Explains the RDA baseline (0.8 g/kg) and why athletes and older adults "
        "often need more.",
        ResourceCategory.NUTRITION,
        "https://www.health.harvard.edu/blog/how-much-protein-do-you-need-every-day-201506188096",
        "Harvard Health Publishing",
    ),
    (
        "Water: How Much Should You Drink Every Day?",
        "Covers daily fluid targets, the factors that raise or lower them "
        "(exercise, climate, health conditions), and myths around the \"8 glasses\" rule.",
        ResourceCategory.NUTRITION,
        "https://www.mayoclinic.org/healthy-lifestyle/nutrition-and-healthy-eating/in-depth/water/art-20044256",
        "Mayo Clinic",
    ),
    (
        "Sleep Hygiene: 8 Tips To Improve Sleep",
        "Eight daily habits -- consistent schedule, limiting screens and caffeine, "
        "a cool dark room -- that make it easier to fall and stay asleep.",
        ResourceCategory.GENERAL,
        "https://health.clevelandclinic.org/sleep-hygiene",
        "Cleveland Clinic",
    ),
    (
        "Adult Activity: An Overview",
        "The official U.S. physical activity guidelines: 150 minutes of "
        "moderate-intensity cardio plus 2 days of muscle-strengthening work per week.",
        ResourceCategory.GENERAL,
        "https://www.cdc.gov/physical-activity-basics/guidelines/adults.html",
        "CDC",
    ),
]


class Command(BaseCommand):
    help = "Seed the resources catalog with a starter set of curated fitness/nutrition articles"

    def handle(self, *args, **options):
        created_count = 0
        for title, summary, category, url, source in STARTER_RESOURCES:
            _, created = Resource.objects.get_or_create(
                title=title,
                defaults={
                    "summary": summary,
                    "category": category,
                    "url": url,
                    "source": source,
                },
            )
            if created:
                created_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {created_count} new resources ({len(STARTER_RESOURCES)} total defined)."
            )
        )