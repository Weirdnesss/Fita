"""
"Is this a food people here actually eat?" -- the one signal the nutrient maths cannot give.

The food database is huge and mostly ingredient-level (PhilFCT lists abalone, ant eggs and a dozen
obscure leaf vegetables next to chicken and rice). Ranking by nutrients alone surfaces whatever has
the best protein per calorie, and ties fall back to alphabetical order, which produced plates of
dried anchovy, abalone and Aurora leaves. So suggestions are also ranked by this reviewable list:

  * STAPLES: common Filipino foods per kind of food. Matching a keyword earns a ranking boost.
    A reviewer can edit the lists; rules.md prints them exactly as they are here.
  * LESS_PREFERRED: dried / salted / smoked foods (high sodium) are ranked lower, never banned.
  * DEPRIORITISED: deli and factory meats (bologna, nuggets, fish balls) and organ meats (liver, tripe, blood)
    are edible but not what a gym beginner expects on a plate: ranked lower, never boosted, never banned.
  * ODD_FOODS: never suggested to a beginner (balut and other embryo eggs, ant eggs, eggnog).
  * NOT_COMMON: look-alikes that match a staple keyword but are not the everyday food (rice cake and
    glutinous rice are not "rice"; lettuce tree is not lettuce; velvet apple is not an apple).
  * Raw foods: PhilFCT lists raw foods under a plain name ("Tilapia", "Chicken white meat", "Potato"), so
    meat, fish, eggs and root crops must name how they were prepared to be suggested. Open Food Facts
    entries are retail products (already cooked, canned or packaged) and are not judged this way.

Foods in groups without a list (soups, snacks) are not judged: they count as common.
"""

import re
import zlib

from nutrition.models import FoodCategory

_C = FoodCategory

# Keyword lists per kind of food. Whole words, case-insensitive, plural "s" allowed.
STAPLES = {
    "protein": (
        "chicken", "pork", "beef", "tilapia", "bangus", "milkfish", "galunggong", "scad", "tuna", "sardine",
        "mackerel", "tulingan", "salmon", "shrimp", "prawn", "squid", "egg", "tofu", "tokwa", "mung bean",
        "monggo", "munggo", "lentil", "chickpea", "peanut", "kidney bean", "black bean",
    ),
    "dairy": ("milk", "yogurt", "yoghurt", "cheese"),
    "carb": (
        "rice", "kanin", "camote", "sweet potato", "potato", "corn", "bread", "pandesal", "pan de sal", "oat", "oatmeal",
        "gabi", "taro", "cassava",
    ),
    "veg": (
        "kangkong", "water spinach", "malunggay", "moringa", "pechay", "pak choi", "bok choy", "cabbage",
        "repolyo", "carrot", "tomato", "eggplant", "talong", "squash", "kalabasa", "ampalaya", "bitter gourd",
        "bitter melon", "sitaw", "string bean", "yardlong", "green bean", "snap bean", "okra", "broccoli",
        "cucumber", "lettuce", "spinach", "sayote", "chayote", "cauliflower", "mustasa", "mustard greens",
        "radish", "saluyot", "alugbati",
        # classic vegetable dishes, filed under vegetables
        "laing", "pinakbet", "chopsuey", "chop suey", "ginisang", "dinengdeng", "ginataang",
    ),
    "fruit": (
        "banana", "saging", "lakatan", "saba", "mango", "papaya", "pineapple", "pinya", "apple", "orange",
        "watermelon", "melon", "guava", "grape", "pear", "dragon fruit", "pomelo", "lanzones", "mandarin",
    ),
}

# Look-alikes that match a keyword above but are not the everyday food. They are never boosted.
NOT_COMMON = {
    "carb": (
        "cake", "glutinous", "puto", "bibingka", "flour", "starch", "bran", "noodle",
        # sweet or filled breads are not the everyday loaf or pan de sal
        "cinnamon", "sweet roll", "pan de coco", "pan de limon", "pan de bonete", "cheese roll", "hotdog roll",
        "filling", "topping", "raisin", "stix",
    ),
    "veg": ("lettuce tree", "new zealand", "radish, pod", "flower", "blossom"),
    "fruit": (
        "velvet apple", "malay apple", "custard apple", "star apple", "rose apple", "wax apple", "love apple",
        "sugar apple", "sweetsop", "monkey apple", "java apple",
    ),
}

CATEGORY_KIND = {
    _C.VIANDS_MEAT: "protein",
    _C.VIANDS_FISH: "protein",
    _C.EGGS: "protein",
    _C.NUTS_LEGUMES: "protein",
    _C.DAIRY: "dairy",
    _C.RICE_GRAINS: "carb",
    _C.ROOTS_TUBERS: "carb",
    _C.VEGETABLES: "veg",
    _C.FRUITS: "fruit",
}

LESS_PREFERRED_WORDS = ("dried", "salted", "smoked", "cured", "tuyo", "daing", "bagoong")
LESS_PREFERRED = re.compile(r"\b(" + "|".join(LESS_PREFERRED_WORDS) + r")\b", re.I)

# Protein foods that are edible but not everyday beginner food. Matched in the protein groups only
# (so "kidney beans" and "heart of palm" are untouched). They count as not common and are ranked lower.
PROCESSED_MEAT_WORDS = (
    "bologna", "salami", "pepperoni", "frankfurter", "pastrami", "jerky", "loaf", "spread", "nugget",
    "meatball", "meat ball", "fish ball", "fish stick", "embotido", "kikiam", "surimi", "imitation",
    "bratwurst", "beerwurst", "liverwurst", "knackwurst", "knockwurst", "cheesefurter", "wiener", "mortadella",
    "headcheese", "liver cheese", "quekiam", "pate", "scrapple", "caviar", "gefilte", "gefiltefish",
)
ORGAN_MEAT_WORDS = (
    "liver", "kidney", "intestine", "tripe", "blood", "brain", "lung", "spleen", "stomach", "tongue", "uterus",
    "gizzard", "heart", "head", "feet", "ear", "isaw", "chicharon",
)
DEPRIORITISED_PATTERN = re.compile(
    r"\b(?:" + "|".join(re.escape(w) for w in PROCESSED_MEAT_WORDS + ORGAN_MEAT_WORDS) + r")s?\b(?!\s+beans?\b)", re.I
)

# Groups where the name must say how the food was prepared, or it is treated as raw and not suggested.
# (Raw chicken or pork is unsafe; raw potato or cassava is not a portion anyone eats.)
MUST_BE_PREPARED = (_C.VIANDS_MEAT, _C.VIANDS_FISH, _C.EGGS, _C.ROOTS_TUBERS)
PREPARED_WORDS = (
    "boiled", "broiled", "fried", "grilled", "roasted", "roast", "baked", "steamed", "cooked", "stewed",
    "braised", "sauteed", "fricassee", "adobo", "tinola", "sinigang", "nilaga", "tapa", "tocino", "longganisa",
    # ready-made or reheated forms
    "rotisserie", "bbq", "barbecue", "barbecued", "heated", "reheated", "scrambled", "poached", "omelet",
    "omelette", "prepared", "prepackaged", "mashed", "kippered",
    "pastrami", "pancake", "pancakes", "salad", "sliced", "deli", "gravy", "blanched", "brined", "glazed",
    "century", "seasoned", "crab cake",
    # preserved or ready-made forms are ready to eat
    "canned", "cnd", "sauce", "sce", "smoked", "dried", "salted", "cured", "corned", "pickled", "bacon", "ham",
    "sausage", "hotdog", "luncheon", "pasteurized",  # pasteurized crab meat is cooked (an egg "raw, pasteurized" still says raw)
)
PREPARED = re.compile(r"\b(?:" + "|".join(PREPARED_WORDS + PROCESSED_MEAT_WORDS) + r")s?\b", re.I)
LABELLED_RAW = re.compile(r"\b(raw|uncooked|unprepared)\b", re.I)
# A name can say "raw" and still hold a ready-word ("ribs prepared, raw"); only a real cooking method overrides raw.
COOKING_METHODS = re.compile(
    r"\b(boiled|broiled|fried|grilled|roasted|baked|steamed|cooked|stewed|braised|sauteed|canned)\b", re.I
)

# Never suggested. "pwdr" is how PhilFCT abbreviates powder (see food_suggester._NOT_READY_ALWAYS).
ODD_FOODS = re.compile(r"\b(embryo|fertili[sz]ed|balut|ants?|eggnog)\b", re.I)

# Ranking weights. Plates use them to pick each part's shortlist; single foods add them to the score.
W_STAPLE_POOL = 0.5
PENALTY_POOL = 0.3
W_STAPLE_SCORE = 0.25
PENALTY_SCORE = 0.15


def _compile(words):
    return re.compile(r"\b(?:" + "|".join(re.escape(w) for w in words) + r")s?\b", re.I)


_PATTERNS = {kind: _compile(words) for kind, words in STAPLES.items()}


_NOT_COMMON_PATTERNS = {kind: _compile(words) for kind, words in NOT_COMMON.items()}

# Desserts, fried snacks and factory patties are never part of a meal plate, even if a reviewer confirms the
# PhilFCT row is cooked (cassava pudding, cassava fritter, chips, pork crackling, hamburger patty).
NOT_A_MEAL_PART_WORDS = ("pudding", "fritter", "suman", "bibingka", "cake", "chips", "crackling", "patty", "patties")
_NOT_A_MEAL_PART = _compile(NOT_A_MEAL_PART_WORDS)


def is_staple(food):
    """True for a common food. Groups without a list (soups, snacks) are not judged and count as common."""
    kind = CATEGORY_KIND.get(food.category)
    if kind is None:
        return True
    if kind in _NOT_COMMON_PATTERNS and _NOT_COMMON_PATTERNS[kind].search(food.name):
        return False
    if kind == "protein" and DEPRIORITISED_PATTERN.search(food.name):
        return False
    return bool(_PATTERNS[kind].search(food.name))


def looks_raw(food):
    """
    Meat, fish, eggs and root crops whose name says nothing about preparation are raw in PhilFCT.
    A user's own foods are trusted: they typed those numbers for something they actually eat.
    """
    if getattr(food, "created_by_id", None):
        return False
    if str(getattr(food, "source", "")).startswith("Open Food Facts"):
        return False  # packaged retail products: already cooked, canned or ready to eat
    if food.category not in MUST_BE_PREPARED:
        return False
    if is_labelled_raw(food) and not COOKING_METHODS.search(food.name):
        return True
    return not PREPARED.search(food.name)


def is_labelled_raw(food):
    """The name itself says raw / uncooked. Such foods are correctly left out and need no review."""
    return bool(LABELLED_RAW.search(food.name))


# Dried egg is a powder (575 kcal per 100 g) and dried or evaporated milk is an ingredient: never a portion of
# breakfast. Dried fish and meat are real foods (tuyo, jerky), so only these groups are judged. Dry-curd
# cottage cheese is a normal cheese.
INGREDIENT_ONLY = {
    _C.EGGS: re.compile(r"\b(dried|pickled)\b", re.I),  # pickled quail eggs are a snack, not a breakfast portion
    _C.DAIRY: re.compile(r"\b(dried|dehydrated|evaporated|condensed|powdered)\b|\bdry\b(?!\s+curd)", re.I),
}


def is_ingredient_only(food):
    pattern = INGREDIENT_ONLY.get(food.category)
    return bool(pattern and pattern.search(food.name))


def less_preferred(food):
    if LESS_PREFERRED.search(food.name):
        return True
    return CATEGORY_KIND.get(food.category) == "protein" and bool(DEPRIORITISED_PATTERN.search(food.name))


def is_odd(food):
    return bool(ODD_FOODS.search(food.name))


def is_not_a_meal_part(food):
    return bool(_NOT_A_MEAL_PART.search(food.name))


def variety_key(food, date):
    """
    Tie-break that is stable within a day but different from day to day, so equal-scoring foods
    rotate instead of always being the alphabetically first ones.
    """
    # crc32 mixes both numbers properly (a linear formula would only shift the whole order each day).
    return zlib.crc32(f"{food.id}:{date.toordinal()}".encode())
