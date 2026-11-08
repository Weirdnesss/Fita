"""
Full-meal ("plate") suggestions: a protein dish + a carb + a vegetable or
fruit that together fit what the user has left today.

Same hybrid design as food_suggester.py. Everything here is rules over
FoodItem rows:

  1. For each plate role (protein / carb / veg / fruit) take the best-looking
     foods from the database -- ready to eat, the right kind of food for that
     role, and favouring what the user already eats.
  2. Try combinations of those foods. For each combination, search the
     realistic portion sizes (e.g. 50-150 g of protein, 50-250 g of rice) for
     the one that best matches the meal's calorie and macro targets, without
     ever going over the day's remaining calories.
  3. Score the plates, keep a varied set (different proteins, not the same
     rice every time).

The LLM (suggestion_llm.py) can only choose among these plates by id and word
the reason; foods and numbers always come from here.

Meal targets: the meal's calorie share (see MEAL_CALORIE_SHARE) capped by
what's left, with protein/carbs/fat targeted in proportion to what's left of
each for the day.
"""

import itertools
import re
from dataclasses import dataclass, field

from django.db.models import Q

from nutrition.models import FoodCategory, FoodItem
from nutrition.services import staples
from nutrition.services.food_suggester import (
    MAX_SERVINGS_SUGGESTED,
    MEAL_CALORIE_SHARE,
    MIN_SERVINGS,
    SERVING_STEP,
    _amount_label,
    _is_ready_to_eat,
    compute_remaining,
    foods_logged_on,
    recent_food_counts,
)

# Not enough left in the day for a whole plate (a protein + a carb is ~170 kcal
# at the smallest realistic portions).
MIN_PLATE_CALORIES = 200
# A plate must reach at least this share of the meal's calorie target, so a
# "lunch" isn't a single boiled egg.
MIN_PLATE_FRACTION = 0.45
# At most this many plates share the same carb / veg, so the list has variety.
MAX_PLATES_PER_SIDE = 2

# Plate score weights (each component 0..1).
W_FIT = 0.65
W_FAMILIAR = 0.15
W_COMPLETE = 0.10
W_FILIPINO = 0.10
# With balance_groups, at most limit // this many plates share a main-item food group (3 plates: one each).
PLATES_PER_MAIN_GROUP_DIVISOR = 3
# Ranking boost for a role's preferred foods (when choosing each part's shortlist).
W_PREFER = 0.4
# Plate score bonus for plates made of a role's preferred foods (egg, tofu, pan de sal...). Without it the
# high-protein meat plates always win and `prefer` only decides who makes the shortlist.
W_PREFERRED = 0.15
# The portion caps in the roles fit a meal of about this many kcal (the biggest plate they allow is ~700).
# Larger meal targets (a 3000 kcal day) widen the protein and carb caps in proportion, up to MAX_PORTION_SCALE,
# or the day's calories can never be reached.
REFERENCE_MEAL_CALORIES = 700
MAX_PORTION_SCALE = 1.5
SCALED_ROLES = ("protein", "main", "carb")  # the plate parts whose upper portion limit grows with the meal
# Cooked cereals (oatmeal, lugaw) are only 60-100 kcal per 100 g: 250 g of them is under 180 kcal and could never
# make a breakfast plate, so a carb below this density may be served in a larger amount.
LOW_DENSITY_KCAL_100 = 100
LOW_DENSITY_PORTION_FACTOR = 1.6
# Only watery foods (oatmeal, lugaw, tofu). Lean meat and canned tuna are also under 100 kcal per 100 g, but are
# 17-20 g protein per 100 g, so stretching their portion would double the protein of the plate.
LOW_DENSITY_MAX_PROTEIN_100 = 12


def is_low_density(kcal_100, protein_100):
    return kcal_100 < LOW_DENSITY_KCAL_100 and protein_100 < LOW_DENSITY_MAX_PROTEIN_100


@dataclass(frozen=True)
class Role:
    name: str
    categories: tuple
    min_g: int  # smallest / largest realistic portion of this item on a plate, in grams
    max_g: int
    required: bool = True
    min_protein_100: float = 0.0  # per 100 g, to count as a protein dish
    min_carbs_100: float = 0.0
    max_fat_100: float = 10_000.0
    max_kcal_100: float = 10_000.0
    pool: int = 8  # how many candidate foods to try for this role
    prefer: tuple = ()  # names containing one of these words are ranked first for this role
    no_canned_in: tuple = ()  # canned foods of these groups are not offered (canned fish or corn is not a breakfast)
    balance_groups: bool = False  # shortlist and plates mix the food groups instead of letting one (cheese) take over
    families: tuple = ()  # word families (rice / bread / oats...): the shortlist takes one food per family in turn
    rotate: tuple = ()  # food groups that share one plate slot; the day picks which gets it first (eggs / tofu at lunch)
    low_density_factor: float = 1.0  # a food under LOW_DENSITY_KCAL_100 may be served this many times max_g (breakfast oats)


_C = FoodCategory
# Lunch and dinner mix the food groups like breakfast does, otherwise only beef, chicken and milkfish ever win.
# max_kcal_100 keeps nuts and seeds (peanuts are ~570 kcal per 100 g) out of the protein slot; tofu, beans, fish,
# eggs and lean meat are all well under it (rich cuts such as fried pork belly are left out too). Dried fish is
# about 320 kcal per 100 g, so the limit stays above it: dried fish is ranked lower, never banned.
PROTEIN = Role(
    "protein", (_C.VIANDS_MEAT, _C.VIANDS_FISH, _C.EGGS, _C.NUTS_LEGUMES), 50, 150, min_protein_100=8, max_kcal_100=350,
    pool=10, balance_groups=True, rotate=(_C.NUTS_LEGUMES, _C.EGGS),
    low_density_factor=LOW_DENSITY_PORTION_FACTOR,  # tofu is ~70 kcal per 100 g; 150 g leaves the plate short
)
BREAKFAST_PROTEIN = Role(
    "protein", (_C.EGGS, _C.DAIRY, _C.VIANDS_MEAT, _C.VIANDS_FISH, _C.NUTS_LEGUMES), 50, 150, min_protein_100=8, pool=10,
    prefer=("egg", "tofu", "tokwa", "yogurt", "yoghurt", "milk", "tapa", "tocino", "longganisa"),
    no_canned_in=(_C.VIANDS_FISH,),
    balance_groups=True,
)
# max_kcal_100: a cooked staple is at most ~210 kcal per 100 g; dry grain, flour or dry pasta is 350+
# and PhilFCT does not mark it as uncooked.
CARB = Role(
    "carb", (_C.RICE_GRAINS, _C.ROOTS_TUBERS), 50, 250, min_carbs_100=12, max_fat_100=12, max_kcal_100=260, pool=6
)
# Bread is 250-335 kcal per 100 g (pan de sal 330), so breakfast allows more than the 260 of lunch and dinner;
# dry grain, dry oats and dry cereal are 345+. Cooked oatmeal is only ~12 g carbs per 100 g, hence the lower minimum.
BREAKFAST_CARB = Role(
    "carb", (_C.RICE_GRAINS, _C.ROOTS_TUBERS), 50, 250, min_carbs_100=10, max_fat_100=12, max_kcal_100=340, pool=8, low_density_factor=LOW_DENSITY_PORTION_FACTOR,
    prefer=("rice", "pandesal", "pan de sal", "bread", "oat", "oatmeal", "camote", "sweet potato", "corn", "porridge", "lugaw",
            "champorado"),
    no_canned_in=(_C.RICE_GRAINS, _C.ROOTS_TUBERS),
    # Rice, corn and camote variants fill the whole shortlist otherwise, and bread and oats never get a plate.
    families=(
        ("rice", "kanin", "lugaw", "porridge", "champorado"),
        ("pandesal", "pan de sal"),
        ("bread",),
        ("oat", "oatmeal"),
        ("camote", "sweet potato"),
        ("corn",),
    ),
)
VEG = Role("veg", (_C.VEGETABLES,), 80, 150, required=False, max_kcal_100=120, pool=6)
FRUIT = Role("fruit", (_C.FRUITS,), 80, 150, required=False, max_kcal_100=120, pool=5)
SNACK_MAIN = Role("main", (_C.DAIRY, _C.EGGS, _C.NUTS_LEGUMES), 50, 200, min_protein_100=6, pool=8)

MEAL_ROLES = {
    "breakfast": (BREAKFAST_PROTEIN, BREAKFAST_CARB, FRUIT),
    "lunch": (PROTEIN, CARB, VEG),
    "dinner": (PROTEIN, CARB, VEG),
    "snack": (SNACK_MAIN, FRUIT),
}

# Things that are in the "vegetables"/"fruits" groups but aren't a side dish.
_NOT_A_SIDE = re.compile(
    r"\b(paste|sauce|juice|powder|pickled?|relish|dried|dehydrated|syrup|candied|canned|drink|nectar|"
    r"jam|jelly|chips|fried|spices?|seasoning|extract|flakes|puree|ketchup|cnd)\b",
    re.I,
)
_AROMATIC = re.compile(
    r"\b(garlic|ginger|chil[il]e?s?|peppers?,? hot|hot peppers?|capers?|horseradish|wasabi|basil|parsley|"
    r"cilantro|coriander|dill|mint|thyme|oregano|rosemary|herbs?|seaweed|shallots?|chives)\b",
    re.I,
)


_CANNED = re.compile(r"\b(canned|cnd|in (natural )?oil|in tomato (sauce|sce)|in brine)\b", re.I)
# Unripe mango (paho) is a sour condiment fruit, not a snack or breakfast side.
_UNRIPE = re.compile(r"\bunripe\b", re.I)
# "dry" cereal (dry oats are 334-380 kcal per 100 g) is an ingredient; the cooked or prepared row is the food.
_DRY = re.compile(r"\bdry\b", re.I)


def _interleave_groups(candidates, pool, key=None):
    """
    Best-first candidates, taken in turns from each food group (the best egg, the best dairy, the best meat...)
    so one group with dozens of dense, common foods (USDA lists a hundred cheeses) cannot fill the whole shortlist.
    `key` maps a food to its group (default: its food category).
    """
    key = key or (lambda food: food.category)
    by_group = {}
    for c in candidates:
        by_group.setdefault(key(c[0]), []).append(c)
    queues = sorted(by_group.values(), key=lambda q: candidates.index(q[0]))
    out = []
    while len(out) < pool and any(queues):
        for q in queues:
            if q and len(out) < pool:
                out.append(q.pop(0))
    return out


def _prefers(food, role):
    if not role.prefer:
        return False
    return bool(re.search(r"\b(?:" + "|".join(re.escape(w) for w in role.prefer) + r")s?\b", food.name, re.I))


def _family(food, role):
    """Index of the first of the role's word families the name belongs to (len(families) when none do)."""
    for index, words in enumerate(role.families):
        if re.search(r"\b(?:" + "|".join(re.escape(w) for w in words) + r")s?\b", food.name, re.I):
            return index
    return len(role.families)


@dataclass
class PlateItem:
    food: FoodItem
    role: str
    servings: float
    calories: float
    protein_g: float
    carbs_g: float
    fat_g: float
    amount_label: str


@dataclass
class Plate:
    items: list
    calories: float
    protein_g: float
    carbs_g: float
    fat_g: float
    score: float
    reason: str = ""
    reason_source: str = "rule"

    @property
    def anchor(self):
        return self.items[0].food

    def item_for(self, role):
        return next((i for i in self.items if i.role == role), None)


@dataclass
class _Targets:
    calories: float
    protein_g: float
    carbs_g: float
    fat_g: float


def _per_100g(food, value):
    return value * 100.0 / max(food.serving_size_g, 1.0)


def portion_scale_for(meal_target):
    """How far the upper portion limits of SCALED_ROLES grow for a meal with this calorie target (1.0 up to 700 kcal)."""
    return min(max(meal_target / REFERENCE_MEAL_CALORIES, 1.0), MAX_PORTION_SCALE)


def _portion_options(food, role, scale=1.0):
    """Servings (in 0.5 steps) whose weight is a realistic amount of this item on a plate (cap widened by `scale`)."""
    size = max(food.serving_size_g, 1.0)
    max_g = role.max_g * scale
    if is_low_density(_per_100g(food, food.calories), _per_100g(food, food.protein_g)):
        max_g *= role.low_density_factor
    options = []
    servings = MIN_SERVINGS
    while servings <= MAX_SERVINGS_SUGGESTED:
        grams = servings * size
        if grams > max_g:
            break
        if grams >= role.min_g:
            options.append(servings)
        servings += SERVING_STEP
    return options


def _fits_role(food, role):
    if food.category not in role.categories or food.calories <= 0:
        return False
    if not _is_ready_to_eat(food) or staples.is_odd(food) or staples.is_not_a_meal_part(food):
        return False
    if role.name == "fruit" and _UNRIPE.search(food.name):
        return False
    if role.name == "carb" and _DRY.search(food.name):
        return False
    if _per_100g(food, food.protein_g) < role.min_protein_100:
        return False
    if _per_100g(food, food.carbs_g) < role.min_carbs_100:
        return False
    if _per_100g(food, food.fat_g) > role.max_fat_100:
        return False
    if _per_100g(food, food.calories) > role.max_kcal_100:
        return False
    if food.category in role.no_canned_in and _CANNED.search(food.name):
        return False
    if role.name in ("veg", "fruit") and _NOT_A_SIDE.search(food.name):
        return False
    if role.name == "veg" and _AROMATIC.search(food.name):
        return False
    return True


def _prerank(food, role, times_eaten):
    """How promising a food looks for a role, before any portions are tried (about -0.3 to 1.5)."""
    score = 0.0
    if role.name in ("protein", "main"):
        density = (_per_100g(food, food.protein_g) * 4) / max(_per_100g(food, food.calories), 1)
        score += 0.6 * min(density / 0.5, 1.0)
    elif role.name == "carb":
        score += 0.4 * max(1 - _per_100g(food, food.fat_g) / 12, 0)
    score += 0.3 * min(times_eaten, 5) / 5
    if food.source.startswith("PhilFCT"):
        score += 0.1
    # Without this the shortlist is the leanest / alphabetically first foods in the database.
    if staples.is_staple(food):
        score += staples.W_STAPLE_POOL
    if staples.less_preferred(food):
        score -= staples.PENALTY_POOL
    if _prefers(food, role):
        score += W_PREFER
    return score


def _loss(calories, protein, carbs, fat, t):
    """How far a plate is from the meal's targets (0 = perfect). Falling short on protein costs the most."""
    loss = abs(calories - t.calories) / t.calories
    if t.protein_g > 5:
        loss += max(t.protein_g - protein, 0) / t.protein_g
        loss += 0.4 * max(protein - 1.5 * t.protein_g, 0) / t.protein_g
    loss += 0.4 * max(carbs - 1.3 * t.carbs_g, 0) / max(t.carbs_g, 30)
    loss += 0.4 * max(fat - 1.3 * t.fat_g, 0) / max(t.fat_g, 15)
    return loss


def _best_portions(chosen, targets, remaining_calories):
    """
    chosen: [(food, portion_options), ...]. Returns (loss, servings_tuple, (cal, p, c, f)) for the
    best allowed portion combination, or None if none fits under the day's remaining calories.
    """
    best = None
    floor = MIN_PLATE_FRACTION * targets.calories
    for servings in itertools.product(*(options for _, options in chosen)):
        calories = protein = carbs = fat = 0.0
        for (food, _), s in zip(chosen, servings):
            calories += food.calories * s
            protein += food.protein_g * s
            carbs += food.carbs_g * s
            fat += food.fat_g * s
        if calories > remaining_calories or calories < floor:
            continue
        loss = _loss(calories, protein, carbs, fat, targets)
        if best is None or loss < best[0]:
            best = (loss, servings, (calories, protein, carbs, fat))
    return best


def _plate_reason(plate, remaining):
    kcal = f"{plate.calories:.0f} kcal"
    if remaining.protein_g > 5:
        share = min(plate.protein_g / remaining.protein_g, 1.0)
        if share >= 0.2:
            return f"About {kcal} with {plate.protein_g:.0f} g protein, {share * 100:.0f}% of the protein you have left."
    return f"A balanced plate of about {kcal}."


def build_meal_suggestions(user, nutrition_profile, meal_type, date, limit=8, exclude_ids=()):
    """
    Returns (remaining, plates), best first. `plates` is empty when there isn't enough left in the day
    for a whole plate, or the database lacks a required kind of food (e.g. no carbs).

    `exclude_ids`: foods already shown. They are skipped as a plate's main item (protein), so "show
    different ideas" gives new plates; side foods can repeat.
    """
    remaining = compute_remaining(nutrition_profile, date)
    if remaining.calories < MIN_PLATE_CALORIES:
        return remaining, []

    meal_target = min(remaining.calories, remaining.goal_calories * MEAL_CALORIE_SHARE[meal_type])
    portion_scale = portion_scale_for(meal_target)
    share = meal_target / remaining.calories
    targets = _Targets(
        calories=meal_target,
        protein_g=remaining.protein_g * share,
        carbs_g=remaining.carbs_g * share,
        fat_g=remaining.fat_g * share,
    )

    roles = MEAL_ROLES[meal_type]
    times_eaten = recent_food_counts(nutrition_profile, date)
    # Variety: a food already eaten today, or already shown, isn't the main item again.
    blocked_main = foods_logged_on(nutrition_profile, date) | set(exclude_ids)

    foods = list(
        FoodItem.objects.filter(category__in={c for r in roles for c in r.categories}, calories__gt=0).filter(
            Q(created_by__isnull=True) | Q(created_by=user)
        )
    )

    pools = []
    for index, role in enumerate(roles):
        candidates = []
        scale = portion_scale if role.name in SCALED_ROLES else 1.0
        for food in foods:
            if not _fits_role(food, role):
                continue
            if index == 0 and food.id in blocked_main:
                continue
            options = _portion_options(food, role, scale)
            if options:
                candidates.append((food, options))
        candidates.sort(
            key=lambda c: (
                -_prerank(c[0], role, times_eaten.get(c[0].id, 0)),
                staples.variety_key(c[0], date),
                c[0].name,
                c[0].id,
            )
        )
        if role.families:
            candidates = _interleave_groups(candidates, role.pool, key=lambda food, role=role: _family(food, role))
        elif role.balance_groups:
            candidates = _interleave_groups(candidates, role.pool)
        candidates = candidates[: role.pool]
        if not candidates and role.required:
            return remaining, []  # can't make a plate without, say, any carb
        pools.append(candidates if role.required else candidates + [None])

    optional_roles = sum(1 for r in roles if not r.required)
    plates = []
    for combo in itertools.product(*pools):
        chosen = [c for c in combo if c is not None]
        best = _best_portions(chosen, targets, remaining.calories)
        if best is None:
            continue
        loss, servings, (calories, protein, carbs, fat) = best

        role_by_food = {c[0].id: role for c, role in zip(combo, roles) if c is not None}
        items = [
            PlateItem(
                food=food,
                role=role_by_food[food.id].name,
                servings=s,
                calories=round(food.calories * s, 1),
                protein_g=round(food.protein_g * s, 1),
                carbs_g=round(food.carbs_g * s, 1),
                fat_g=round(food.fat_g * s, 1),
                amount_label=_amount_label(food, s),
            )
            for (food, _), s in zip(chosen, servings)
        ]

        familiar = sum(min(times_eaten.get(i.food.id, 0), 5) / 5 for i in items) / len(items)
        filipino = sum(1 for i in items if i.food.source.startswith("PhilFCT") or i.food.created_by_id) / len(items)
        complete = (len(items) - (len(roles) - optional_roles)) / optional_roles if optional_roles else 1.0
        liked = [c is not None and _prefers(c[0], r) for c, r in zip(combo, roles) if r.prefer]
        preferred = sum(liked) / len(liked) if liked else 0.0
        score = (
            W_FIT / (1 + loss)
            + W_FAMILIAR * familiar
            + W_COMPLETE * complete
            + W_FILIPINO * filipino
            + W_PREFERRED * preferred
        )

        plates.append(
            Plate(
                items=items,
                calories=round(calories, 1),
                protein_g=round(protein, 1),
                carbs_g=round(carbs, 1),
                fat_g=round(fat, 1),
                score=round(score, 4),
            )
        )

    def order(p):
        # Equal scores rotate from day to day (staples.variety_key) instead of following the alphabet.
        return (-p.score, [staples.variety_key(i.food, date) for i in p.items], [i.food.name for i in p.items])

    def rotated_out(p):
        # Of the groups that share a slot (tofu/legumes, eggs), only the day's turn ranks normally;
        # the others rank after everything else, so they still fill in when nothing else is left.
        rotate = roles[0].rotate
        if not rotate or p.anchor.category not in rotate:
            return False
        turn = rotate[(date.toordinal() + (meal_type == "dinner")) % len(rotate)]
        return p.anchor.category != turn

    plates.sort(key=lambda p: (rotated_out(p), order(p)))

    # Variety, as a preference rather than a hard rule: first pass keeps one plate per main item and
    # at most MAX_PLATES_PER_SIDE plates sharing the same carb/veg; if that leaves fewer than `limit`
    # (a small food database), a second pass fills up with the best remaining plates.
    picked, mains, sides, groups = [], set(), {}, {}
    group_cap = max(1, limit // PLATES_PER_MAIN_GROUP_DIVISOR)
    for strict in (True, False):
        for plate in plates:
            if len(picked) >= limit:
                break
            if plate in picked or plate.anchor.id in mains:
                continue
            side_ids = [i.food.id for i in plate.items[1:]]
            if strict and any(sides.get(sid, 0) >= MAX_PLATES_PER_SIDE for sid in side_ids):
                continue
            if strict and roles[0].balance_groups and groups.get(plate.anchor.category, 0) >= group_cap:
                continue
            groups[plate.anchor.category] = groups.get(plate.anchor.category, 0) + 1
            mains.add(plate.anchor.id)
            for sid in side_ids:
                sides[sid] = sides.get(sid, 0) + 1
            picked.append(plate)
    picked.sort(key=order)

    for plate in picked:
        plate.reason = _plate_reason(plate, remaining)
    return remaining, picked
