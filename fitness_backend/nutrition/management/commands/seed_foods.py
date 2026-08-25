"""
Seeds a starter Filipino food database.

IMPORTANT: These calorie/macro values are reasonable estimates based on
typical preparations and general nutrition knowledge -- they are NOT
transcribed from PhilFCT's published tables (no bulk PhilFCT dataset
was available). Before using these numbers in your thesis Results,
cross-check each entry against the PhilFCT Online Database
(https://i.fnri.dost.gov.ph/fct/library/search_item) or your FNRI FOI
response, and update the `source` field accordingly (e.g. from
"estimated" to "PhilFCT 2019, item #XXXX"). This keeps your dataset
citable and your methodology defensible.

Run with: python manage.py seed_foods
"""

from django.core.management.base import BaseCommand

from nutrition.models import FoodCategory, FoodItem

STARTER_FOODS = [
    # name, local_name, category, serving_description, serving_size_g,
    # calories, protein_g, carbs_g, fat_g
    ("Steamed Rice", "Kanin", FoodCategory.RICE_GRAINS, "1 cup cooked", 160, 205, 4.3, 45, 0.4),
    ("Fried Rice", "Sinangag", FoodCategory.RICE_GRAINS, "1 cup", 175, 250, 4.5, 44, 6.5),
    ("Rice Porridge", "Lugaw/Champorado base", FoodCategory.RICE_GRAINS, "1 cup", 200, 140, 2.5, 30, 0.5),

    ("Chicken Adobo", "Adobong Manok", FoodCategory.VIANDS_MEAT, "1 cup (with sauce)", 200, 320, 25, 4, 22),
    ("Pork Adobo", "Adobong Baboy", FoodCategory.VIANDS_MEAT, "1 cup (with sauce)", 200, 400, 24, 4, 31),
    ("Pork Sinigang", "Sinigang na Baboy", FoodCategory.SOUPS, "1 bowl", 350, 280, 20, 12, 17),
    ("Beef Caldereta", "Kaldereta", FoodCategory.VIANDS_MEAT, "1 cup", 220, 350, 22, 10, 24),
    ("Chicken Tinola", "Tinolang Manok", FoodCategory.SOUPS, "1 bowl", 350, 190, 20, 8, 8),
    ("Pork Menudo", "Menudo", FoodCategory.VIANDS_MEAT, "1 cup", 220, 300, 18, 15, 18),
    ("Beef Tapa", "Tapa", FoodCategory.VIANDS_MEAT, "3 oz strips", 85, 230, 24, 3, 13),
    ("Lechon Kawali", "Lechon Kawali", FoodCategory.VIANDS_MEAT, "3 pieces", 100, 380, 20, 2, 32),
    ("Grilled Pork Belly", "Inihaw na Liempo", FoodCategory.VIANDS_MEAT, "3 oz", 85, 330, 18, 0, 28),
    ("Fried Chicken", "Fried Chicken", FoodCategory.VIANDS_MEAT, "1 piece (thigh)", 120, 280, 22, 8, 17),
    ("Longganisa", "Longganisa", FoodCategory.VIANDS_MEAT, "2 links", 90, 240, 12, 6, 18),

    ("Fried Bangus", "Pritong Bangus", FoodCategory.VIANDS_FISH, "1 fillet", 150, 240, 28, 0, 13),
    ("Fried Tilapia", "Pritong Tilapia", FoodCategory.VIANDS_FISH, "1 piece (medium)", 150, 190, 30, 0, 7),
    ("Sinigang na Isda", "Fish Sinigang", FoodCategory.SOUPS, "1 bowl", 350, 180, 20, 10, 6),
    ("Bangus Sisig", "Sisig na Bangus", FoodCategory.VIANDS_FISH, "1 cup", 200, 260, 22, 6, 16),
    ("Grilled Bangus", "Inihaw na Bangus", FoodCategory.VIANDS_FISH, "1 fillet", 150, 210, 28, 0, 10),
    ("Pork Sisig", "Sisig", FoodCategory.VIANDS_MEAT, "1 cup", 200, 400, 25, 5, 30),

    ("Pinakbet", "Pinakbet", FoodCategory.VEGETABLES, "1 cup", 200, 120, 5, 14, 5),
    ("Chopsuey", "Chopsuey", FoodCategory.VEGETABLES, "1 cup", 200, 110, 6, 10, 5),
    ("Laing", "Laing", FoodCategory.VEGETABLES, "1 cup", 200, 210, 5, 10, 17),
    ("Ginisang Monggo", "Monggo Guisado", FoodCategory.VEGETABLES, "1 cup", 200, 180, 12, 25, 4),
    ("Ampalaya with Egg", "Ginisang Ampalaya", FoodCategory.VEGETABLES, "1 cup", 200, 130, 7, 8, 8),
    ("Kangkong Guisado", "Sauteed Water Spinach", FoodCategory.VEGETABLES, "1 cup", 150, 80, 3, 6, 5),

    ("Banana", "Saging (Lakatan)", FoodCategory.FRUITS, "1 medium", 100, 90, 1.1, 23, 0.3),
    ("Mango", "Mangga", FoodCategory.FRUITS, "1 cup sliced", 165, 100, 1.4, 25, 0.6),
    ("Papaya", "Papaya", FoodCategory.FRUITS, "1 cup cubed", 145, 62, 0.7, 16, 0.2),
    ("Watermelon", "Pakwan", FoodCategory.FRUITS, "1 cup diced", 150, 46, 0.9, 11.5, 0.2),

    ("Pancit Canton", "Pancit Canton", FoodCategory.SNACKS, "1 cup", 200, 280, 10, 38, 9),
    ("Pancit Bihon", "Pancit Bihon", FoodCategory.SNACKS, "1 cup", 200, 230, 6, 40, 6),
    ("Lumpiang Shanghai", "Lumpia", FoodCategory.SNACKS, "4 pieces", 100, 220, 8, 16, 14),
    ("Empanada", "Empanada", FoodCategory.SNACKS, "1 piece", 120, 300, 8, 30, 17),
    ("Siopao Asado", "Siopao", FoodCategory.SNACKS, "1 piece (large)", 150, 320, 12, 48, 9),
    ("Turon", "Turon", FoodCategory.DESSERTS, "1 piece", 80, 180, 1.5, 30, 6),
    ("Halo-Halo", "Halo-Halo", FoodCategory.DESSERTS, "1 regular cup", 300, 350, 5, 65, 8),
    ("Leche Flan", "Leche Flan", FoodCategory.DESSERTS, "1 slice", 90, 220, 5, 30, 9),
    ("Bibingka", "Bibingka", FoodCategory.DESSERTS, "1 slice", 100, 200, 4, 32, 6),
    ("Puto", "Puto", FoodCategory.SNACKS, "3 pieces", 90, 150, 3, 30, 2),

    ("Calamansi Juice", "Calamansi Juice", FoodCategory.BEVERAGES, "1 glass (unsweetened)", 240, 40, 0.5, 10, 0.1),
    ("Sago't Gulaman", "Sago't Gulaman", FoodCategory.BEVERAGES, "1 glass", 300, 180, 0.2, 46, 0.1),
    ("Buko Juice", "Buko Juice", FoodCategory.BEVERAGES, "1 glass (fresh)", 240, 45, 0.5, 9, 0.5),

    ("Toyo (Soy Sauce)", "Toyo", FoodCategory.CONDIMENTS, "1 tbsp", 15, 10, 1, 1, 0),
    ("Suka (Vinegar)", "Suka", FoodCategory.CONDIMENTS, "1 tbsp", 15, 3, 0, 0.1, 0),
    ("Bagoong", "Bagoong", FoodCategory.CONDIMENTS, "1 tbsp", 15, 20, 2, 1, 1),
]


class Command(BaseCommand):
    help = "Seed the local Filipino food database with a starter set of common dishes"

    def handle(self, *args, **options):
        created_count = 0
        for row in STARTER_FOODS:
            (
                name,
                local_name,
                category,
                serving_description,
                serving_size_g,
                calories,
                protein_g,
                carbs_g,
                fat_g,
            ) = row
            _, created = FoodItem.objects.get_or_create(
                name=name,
                serving_description=serving_description,
                defaults={
                    "local_name": local_name,
                    "category": category,
                    "serving_size_g": serving_size_g,
                    "calories": calories,
                    "protein_g": protein_g,
                    "carbs_g": carbs_g,
                    "fat_g": fat_g,
                    "source": "estimated (verify against PhilFCT before publishing)",
                },
            )
            if created:
                created_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {created_count} new food items ({len(STARTER_FOODS)} total defined)."
            )
        )
