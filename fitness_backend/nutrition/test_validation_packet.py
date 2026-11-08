"""
Tests for the expert-validation packet (nutrition/services/validation_packet.py and
`manage.py export_validation_packet`): the rules file must follow the live constants, the
sample-plate run must never write to the database, and the audit must actually catch problems.
"""

import csv
import io
import tempfile
from pathlib import Path
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from .models import FoodEntry, FoodItem, NutritionProfile
from .services import food_suggester as fs
from .services import staples
from .services import validation_packet as vp
from .test_meal_suggestions import make_food

Account = get_user_model()


def plate_item(role="carb", grams=100, kcal=130, protein=2.7, carbs=28, fat=0.3, food="Rice, cooked"):
    return {"role": role, "grams": grams, "kcal": kcal, "protein_g": protein, "carbs_g": carbs, "fat_g": fat, "food": food}


class FoodsMixin:
    def make_foods(self):
        make_food("Chicken breast, cooked", "viands_meat", 165, 31, 0, 3.6)
        make_food("Tilapia, cooked", "viands_fish", 128, 26, 0, 2.7)
        make_food("Rice, cooked", "rice_grains", 130, 2.7, 28, 0.3, source="Estimated composite dish")
        make_food("Camote, baked", "roots_tubers", 90, 2, 20.7, 0.15)
        make_food("Kangkong, cooked", "vegetables", 19, 2.6, 3.1, 0.2, source="USDA FoodData Central, item 1")
        make_food("Banana", "fruits", 89, 1.1, 22.8, 0.3, source="Estimated composite dish")
        make_food("Greek yogurt", "dairy", 97, 9, 3.9, 5, source="Open Food Facts, barcode 1")
        make_food("Tofu, firm", "nuts_legumes", 144, 15.8, 3.9, 8.7)


class RulesTests(TestCase):
    def test_fingerprint_is_stable(self):
        self.assertEqual(vp.build_rules_md()[1], vp.build_rules_md()[1])

    def test_rules_show_the_live_numbers(self):
        text, _ = vp.build_rules_md()
        for meal, share in fs.MEAL_CALORIE_SHARE.items():
            self.assertIn(f"| {meal.title()} | {round(share * 100)}% |", text)
        for category, grams in fs.MAX_PORTION_G.items():
            self.assertIn(f"| {category.label} | {grams} g |", text)
        self.assertIn(f"less than {vp.mb.MIN_PLATE_CALORIES} kcal", text)

    def test_changing_a_rule_changes_the_fingerprint_and_the_text(self):
        before_text, before = vp.build_rules_md()
        caps = dict(fs.MAX_PORTION_G)
        caps[fs.FoodCategory.VIANDS_MEAT] = 120
        with mock.patch.object(fs, "MAX_PORTION_G", caps):
            text, after = vp.build_rules_md()
        self.assertNotEqual(before, after)
        self.assertIn("| Viands - Meat & Poultry | 120 g |", text)
        self.assertNotIn("| Viands - Meat & Poultry | 120 g |", before_text)

    def test_rules_print_the_common_foods_list_exactly(self):
        text, _ = vp.build_rules_md()
        self.assertIn("## 9. Common foods are ranked first", text)
        for words in staples.STAPLES.values():
            self.assertIn(", ".join(words), text)
        self.assertIn(", ".join(staples.LESS_PREFERRED_WORDS), text)
        self.assertIn(staples.ODD_FOODS.pattern, text)

    def test_editing_the_common_foods_list_changes_the_fingerprint(self):
        _, before = vp.build_rules_md()
        edited = {**staples.STAPLES, "fruit": staples.STAPLES["fruit"] + ("rambutan",)}
        with mock.patch.object(staples, "STAPLES", edited):
            text, after = vp.build_rules_md()
        self.assertNotEqual(before, after)
        self.assertIn("rambutan", text)

    def test_changing_the_staple_boost_changes_the_fingerprint(self):
        _, before = vp.build_rules_md()
        with mock.patch.object(staples, "W_STAPLE_POOL", 0.9):
            _, after = vp.build_rules_md()
        self.assertNotEqual(before, after)

    def test_changing_a_plate_range_changes_the_fingerprint(self):
        _, before = vp.build_rules_md()
        with mock.patch.object(vp.mb, "MIN_PLATE_FRACTION", 0.6):
            _, after = vp.build_rules_md()
        self.assertNotEqual(before, after)

    def test_fingerprint_covers_the_rules_only_not_the_date(self):
        body, _ = vp.build_rules_md()
        self.assertNotRegex(body, r"\d{4}-\d{2}-\d{2}")


class AuditTests(TestCase):
    def audit(self, items=None, plate_kcal=500, remaining=1000, target=500, meal="lunch"):
        return vp.audit_plate(items or [plate_item()], plate_kcal, remaining, target, meal)

    def test_a_good_plate_has_no_flags(self):
        self.assertEqual(self.audit(), [])

    def test_flags_a_plate_that_is_too_small_for_its_meal(self):
        flags = self.audit(plate_kcal=200, target=500)  # 40% < 45%
        self.assertTrue(any("under 45%" in f for f in flags), flags)

    def test_a_small_snack_is_fine_when_the_target_is_small(self):
        self.assertEqual(self.audit(plate_kcal=120, remaining=1500, target=150, meal="snack",
                                    items=[plate_item(role="main", grams=100, kcal=120, protein=10, carbs=5, fat=6)]), [])

    def test_flags_a_plate_over_the_calories_left(self):
        flags = self.audit(plate_kcal=900, remaining=800, target=800)
        self.assertIn("plate over the calories left today", flags)

    def test_flags_a_portion_over_the_plate_limit(self):
        flags = self.audit(items=[plate_item(role="carb", grams=300, kcal=390, protein=8, carbs=84, fat=1)])
        self.assertTrue(any("over the 250 g plate limit" in f for f in flags), flags)

    def test_the_limit_is_exact_not_off_by_one(self):
        self.assertEqual(self.audit(items=[plate_item(role="carb", grams=250, kcal=325, protein=7, carbs=70, fat=1)]), [])

    def test_flags_calories_that_do_not_match_the_macros(self):
        flags = self.audit(items=[plate_item(kcal=400, protein=2, carbs=10, fat=1)])  # macros imply ~57 kcal
        self.assertTrue(any("calories and macros disagree" in f for f in flags), flags)

    def test_macro_check_skips_tiny_foods(self):
        self.assertTrue(vp.macros_match_kcal(10, 0, 0, 0))

    def test_macro_tolerance_edges(self):
        self.assertTrue(vp.macros_match_kcal(100, 0, 15, 0))   # macros imply 60 kcal: exactly 40% off, allowed
        self.assertFalse(vp.macros_match_kcal(100, 0, 14, 0))  # imply 56 kcal: 44% off
        self.assertTrue(vp.macros_match_kcal(100, 0, 0, 12))   # imply 108 kcal: 8% off

    def test_flags_a_food_that_is_not_on_the_common_foods_list(self):
        item = dict(plate_item(food="Aurora lvs"), common=False)
        flags = self.audit(items=[item])
        self.assertIn("Aurora lvs: not on the common-foods list", flags)

    def test_a_common_food_is_not_flagged(self):
        self.assertEqual(self.audit(items=[dict(plate_item(), common=True)]), [])

    def test_snack_part_uses_its_own_limit(self):
        flags = self.audit(meal="snack", target=150, plate_kcal=150, remaining=1500,
                           items=[plate_item(role="main", grams=250, kcal=150, protein=15, carbs=5, fat=8)])
        self.assertTrue(any("over the 200 g plate limit" in f for f in flags), flags)


class SamplePlateTests(FoodsMixin, TestCase):
    def setUp(self):
        self.make_foods()

    def test_builds_plates_and_never_writes_to_the_database(self):
        users, profiles, entries = Account.objects.count(), NutritionProfile.objects.count(), FoodEntry.objects.count()
        foods = FoodItem.objects.count()
        rows = vp.build_sample_rows(goals=(2000,), meals=("lunch", "dinner"))
        self.assertTrue([r for r in rows if r["option"]])
        self.assertEqual(Account.objects.count(), users)
        self.assertEqual(NutritionProfile.objects.count(), profiles)
        self.assertEqual(FoodEntry.objects.count(), entries)
        self.assertEqual(FoodItem.objects.count(), foods)

    def test_rolls_back_even_when_the_builder_fails(self):
        users = Account.objects.count()
        with mock.patch.object(vp.mb, "build_meal_suggestions", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                vp.build_sample_rows(goals=(2000,), meals=("lunch",))
        self.assertEqual(Account.objects.count(), users)

    def test_a_private_custom_food_never_appears(self):
        owner = Account.objects.create_user(email="owner@test.com", password="pass12345")
        make_food("Secret Adobo", "viands_meat", 400, 60, 0, 20, created_by=owner)
        rows = vp.build_sample_rows(goals=(2000,), meals=("lunch",))
        self.assertNotIn("Secret Adobo", {r.get("food") for r in rows})

    def test_rows_carry_grams_and_plate_totals(self):
        rows = [r for r in vp.build_sample_rows(goals=(2000,), meals=("lunch",)) if r["option"]]
        self.assertTrue(rows)
        for r in rows:
            self.assertGreater(r["grams"], 0)
            self.assertGreater(r["plate_kcal"], 0)
        plate1 = [r for r in rows if r["option"] == 1]
        self.assertAlmostEqual(sum(r["kcal"] for r in plate1), plate1[0]["plate_kcal"], delta=len(plate1))

    def test_clean_run_on_a_valid_database_has_no_flags(self):
        rows = vp.build_sample_rows(goals=(1500, 2200), meals=vp.MEALS)
        self.assertEqual([r["flags"] for r in rows if r.get("flags")], [])

    def test_every_row_says_whether_the_food_is_common(self):
        rows = [r for r in vp.build_sample_rows(goals=(2000,), meals=("lunch",)) if r["option"]]
        self.assertTrue(rows)
        self.assertEqual({r["common_food"] for r in rows}, {"yes"})
        self.assertIn("common_food", vp.SAMPLE_COLUMNS)

    def test_a_scenario_with_no_possible_plate_is_reported_not_dropped(self):
        FoodItem.objects.filter(category__in=["rice_grains", "roots_tubers"]).delete()  # no carbs at all
        rows = vp.build_sample_rows(goals=(2000,), meals=("lunch",))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["flags"], "no plate could be built")
        self.assertEqual(rows[0]["option"], 0)

    def test_the_audit_runs_on_real_output_and_would_notice_a_bad_plate(self):
        # Break the builder's portion rule and confirm the packet shows flags.
        wide = vp.mb.Role("carb", vp.mb.CARB.categories, 50, 600, min_carbs_100=12, max_fat_100=12, pool=6)
        roles = dict(vp.mb.MEAL_ROLES)
        roles["lunch"] = (vp.mb.PROTEIN, wide, vp.mb.VEG)
        limits = vp.plate_part_limits()  # audited against the ORIGINAL rules
        with mock.patch.object(vp.mb, "MEAL_ROLES", roles), mock.patch.object(vp, "plate_part_limits", return_value=limits):
            rows = vp.build_sample_rows(goals=(3000,), meals=("lunch",))
        flags = " ".join(r["flags"] for r in rows if r.get("flags"))
        self.assertIn("plate limit", flags)


class EstimatedFoodsTests(FoodsMixin, TestCase):
    def setUp(self):
        self.make_foods()

    def rows(self, used=None):
        return vp.build_estimated_rows(used or {})

    def test_lists_only_foods_that_cite_no_published_table(self):
        names = {r["name"] for r in self.rows()}
        self.assertEqual(names, {"Rice, cooked", "Banana"})

    def test_excludes_user_foods(self):
        owner = Account.objects.create_user(email="o@test.com", password="pass12345")
        make_food("My Estimate", "snacks", 100, 1, 1, 1, source="whatever", created_by=owner)
        self.assertNotIn("My Estimate", {r["name"] for r in self.rows()})

    def test_most_used_first(self):
        # "Rice, cooked" sorts after "Banana" alphabetically, so only the usage sort puts it first
        rice = FoodItem.objects.get(name="Rice, cooked")
        rows = self.rows({rice.id: 5})
        self.assertEqual([r["name"] for r in rows], ["Rice, cooked", "Banana"])
        self.assertEqual(rows[0]["times_in_sample_plates"], 5)

    def test_ties_are_sorted_by_name(self):
        self.assertEqual([r["name"] for r in self.rows()], ["Banana", "Rice, cooked"])

    def test_marks_foods_whose_macros_contradict_their_calories(self):
        make_food("Bad Entry", "snacks", 500, 1, 1, 1, source="Estimated")
        by_name = {r["name"]: r for r in self.rows()}
        self.assertEqual(by_name["Bad Entry"]["macros_vs_kcal"], "DISAGREE")
        self.assertEqual(by_name["Rice, cooked"]["macros_vs_kcal"], "ok")

    def test_verdict_columns_start_empty(self):
        row = self.rows()[0]
        for column in vp.ESTIMATED_COLUMNS:
            if column.startswith("reviewer") or column.startswith("corrected"):
                self.assertEqual(row[column], "")


class PacketFilesTests(FoodsMixin, TestCase):
    def setUp(self):
        self.make_foods()
        make_food("Pritong Isda", "viands_fish", 200, 22, 0, 12, source="Estimated", local_name="Isdang Prito ñ")

    def test_write_packet_creates_all_five_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            packet = vp.build_packet(goals=(2000,), meals=("lunch",))
            out = vp.write_packet(packet, Path(tmp) / "nested" / "packet")
            self.assertEqual({p.name for p in out.iterdir()},
                             {"rules.md", "summary.md", "sample_plates.csv", "estimated_foods.csv", "raw_looking_foods.csv"})
            self.assertIn(packet.fingerprint, (out / "rules.md").read_text(encoding="utf-8"))
            self.assertIn(packet.fingerprint, (out / "summary.md").read_text(encoding="utf-8"))

    def test_csvs_have_the_documented_headers_and_keep_filipino_characters(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = vp.write_packet(vp.build_packet(goals=(2000,), meals=("lunch",)), tmp)
            with open(out / "estimated_foods.csv", encoding="utf-8-sig", newline="") as f:
                reader = csv.DictReader(f)
                self.assertEqual(reader.fieldnames, vp.ESTIMATED_COLUMNS)
                local = [r["local_name"] for r in reader]
            self.assertIn("Isdang Prito ñ", local)
            with open(out / "sample_plates.csv", encoding="utf-8-sig", newline="") as f:
                self.assertEqual(csv.DictReader(f).fieldnames, vp.SAMPLE_COLUMNS)

    def test_summary_counts_match_the_files(self):
        packet = vp.build_packet(goals=(2000,), meals=("lunch", "dinner"))
        plates = {(r["scenario"], r["option"]) for r in packet.sample_rows if r["option"]}
        self.assertEqual(packet.stats["plates"], len(plates))
        self.assertIn(f"{len(plates)} sample plates", packet.summary_md)
        self.assertIn(f"{packet.stats['estimated_foods']} foods that cite no published table", packet.summary_md)

    def test_same_database_gives_the_same_fingerprint(self):
        a = vp.build_packet(goals=(2000,), meals=("lunch",))
        b = vp.build_packet(goals=(2000,), meals=("lunch",))
        self.assertEqual(a.fingerprint, b.fingerprint)


class RawFoodsListTests(FoodsMixin, TestCase):
    def setUp(self):
        self.make_foods()
        make_food("Chicken white meat", "viands_meat", 120, 23, 0, 2.5)        # raw, common name
        make_food("Pritong Isda", "viands_fish", 200, 22, 0, 12, local_name="x")  # raw-looking, uncommon name
        make_food("Potato", "roots_tubers", 77, 2, 17, 0.1)
        make_food("Potato, boiled", "roots_tubers", 87, 1.9, 20, 0.1)         # cooked: not listed
        owner = Account.objects.create_user(email="o@test.com", password="pass12345")
        make_food("My raw thing", "viands_meat", 100, 20, 0, 2, created_by=owner)  # user food: never listed

    def test_lists_shared_foods_that_look_raw_and_nothing_else(self):
        names = {r["name"] for r in vp.build_raw_rows()}
        self.assertEqual(names, {"Chicken white meat", "Pritong Isda", "Potato"})

    def test_common_names_come_first_and_verdict_is_blank(self):
        rows = vp.build_raw_rows()
        flags = [r["named_like_a_common_food"] for r in rows]
        self.assertEqual(flags, sorted(flags, reverse=True))  # "yes" before "no"
        self.assertEqual(rows[-1]["name"], "Pritong Isda")
        self.assertEqual(rows[0]["reviewer_verdict (really raw / actually cooked)"], "")

    def test_summary_counts_them_and_points_to_the_file(self):
        packet = vp.build_packet(goals=(2000,), meals=("lunch",))
        self.assertIn("(treated as raw): 3, of which 2 have common names", packet.summary_md)
        self.assertIn("raw_looking_foods.csv", packet.summary_md)
        self.assertEqual(packet.stats["raw_looking_foods"], 3)

    def test_file_has_the_documented_columns(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = vp.write_packet(vp.build_packet(goals=(2000,), meals=("lunch",)), tmp)
            with open(out / "raw_looking_foods.csv", encoding="utf-8-sig", newline="") as f:
                reader = csv.DictReader(f)
                self.assertEqual(reader.fieldnames, vp.RAW_COLUMNS)
                self.assertEqual(len(list(reader)), 3)

    def test_rules_state_the_raw_rule_and_the_lookalikes(self):
        text, _ = vp.build_rules_md()
        self.assertIn("Treated as raw and not suggested", text)
        self.assertIn(", ".join(staples.PREPARED_WORDS), text)
        self.assertIn("Foods a user added themselves, and Open Food Facts products (packaged retail items), are not judged this way.", text)
        self.assertIn("Not counted as common even when the name matches", text)
        for words in staples.NOT_COMMON.values():
            self.assertIn("; ".join(words), text)

    def test_changing_the_raw_rule_or_lookalikes_changes_the_fingerprint(self):
        _, before = vp.build_rules_md()
        with mock.patch.object(staples, "PREPARED_WORDS", staples.PREPARED_WORDS + ("poached",)):
            _, after_words = vp.build_rules_md()
        with mock.patch.object(staples, "NOT_COMMON", {**staples.NOT_COMMON, "fruit": ("jackfruit",)}):
            _, after_lookalikes = vp.build_rules_md()
        self.assertEqual(len({before, after_words, after_lookalikes}), 3)


class CommandTests(FoodsMixin, TestCase):
    def run_command(self, *args):
        out, err = io.StringIO(), io.StringIO()
        call_command("export_validation_packet", *args, stdout=out, stderr=err)
        return out.getvalue(), err.getvalue()

    def test_writes_the_packet_to_the_chosen_folder(self):
        self.make_foods()
        with tempfile.TemporaryDirectory() as tmp:
            out, _ = self.run_command("--out", str(Path(tmp) / "p"))
            self.assertIn("rules fingerprint:", out)
            self.assertIn("foods left out as raw-looking:", out)
            self.assertTrue((Path(tmp) / "p" / "rules.md").exists())

    def test_empty_database_explains_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, err = self.run_command("--out", str(Path(tmp) / "p"))
            self.assertIn("food database is empty", err)
            self.assertFalse((Path(tmp) / "p").exists())

    def test_only_private_foods_counts_as_empty(self):
        owner = Account.objects.create_user(email="o@test.com", password="pass12345")
        make_food("Mine", "snacks", 100, 1, 1, 1, created_by=owner)
        with tempfile.TemporaryDirectory() as tmp:
            _, err = self.run_command("--out", str(Path(tmp) / "p"))
            self.assertIn("food database is empty", err)


class CommonFoodsReviewTests(TestCase):
    """The packet must show a reviewer when plates are made of foods nobody would recognise."""

    def setUp(self):
        make_food("Abalone, boiled", "viands_fish", 120, 20, 3, 2)
        make_food("Arrowroot, boiled", "roots_tubers", 140, 3, 32, 0.1)
        make_food("Aurora lvs", "vegetables", 40, 3, 7, 0.4)

    def test_plates_of_uncommon_foods_are_flagged_and_counted(self):
        rows = [r for r in vp.build_sample_rows(goals=(2200,), meals=("lunch",)) if r["option"]]
        self.assertTrue(rows)
        self.assertEqual({r["common_food"] for r in rows}, {"no"})
        self.assertIn("not on the common-foods list", rows[0]["flags"])

    def test_the_summary_reports_the_share_of_common_plate_parts(self):
        packet = vp.build_packet(goals=(2200,), meals=("lunch",))
        parts = [r for r in packet.sample_rows if r.get("food_id")]
        self.assertIn(f"Plate parts on the common-foods list: 0 of {len(parts)}", packet.summary_md)

    def test_the_summary_does_not_say_start_there_when_no_estimated_food_is_used(self):
        packet = vp.build_packet(goals=(2200,), meals=("lunch",))
        self.assertNotIn("start there", packet.summary_md)
        self.assertIn("None; every food cites a published table.", packet.summary_md)


class LabelledRawTests(TestCase):
    """Foods whose name literally says raw are correct to leave out, so they are counted, not listed."""

    def setUp(self):
        make_food("Chicken, broiler, breast, raw", "viands_meat", 120, 23, 0, 2.5, source="USDA Foods, 1")
        make_food("Egg, whole, uncooked", "eggs", 143, 12.6, 0.7, 9.5, source="USDA Foods, 2")
        make_food("Chicken white meat", "viands_meat", 120, 23, 0, 2.5)           # plain name: listed
        make_food("Chicken, rotisserie", "viands_meat", 200, 25, 0, 10)           # ready now: neither
        make_food("Tilapia, fried", "viands_fish", 160, 27, 0, 5.7)               # cooked: neither
        make_food("Apple, raw", "fruits", 52, 0.3, 14, 0.2)                       # raw fruit is fine to eat: not counted
        make_food("Pork loin, cooked, from raw", "viands_meat", 200, 25, 0, 10)   # cooked: not counted
        owner = Account.objects.create_user(email="o2@test.com", password="pass12345")
        make_food("My raw chicken", "viands_meat", 100, 20, 0, 2, created_by=owner)  # private: neither

    def test_labelled_raw_foods_are_not_listed_but_plain_names_are(self):
        self.assertEqual([r["name"] for r in vp.build_raw_rows()], ["Chicken white meat"])

    def test_labelled_raw_foods_are_counted(self):
        self.assertEqual(vp.count_labelled_raw(), 2)

    def test_summary_and_stats_report_both_numbers(self):
        packet = vp.build_packet(goals=(2000,), meals=("lunch",))
        self.assertEqual(packet.stats["raw_looking_foods"], 1)
        self.assertEqual(packet.stats["labelled_raw_foods"], 2)
        self.assertIn("name itself says raw or uncooked: 2 (correct, not listed)", packet.summary_md)

    def test_rules_describe_the_new_ranking_and_exemptions(self):
        rules = vp.build_packet(goals=(2000,), meals=("lunch",)).rules_md
        self.assertIn("organ meats:", rules)
        self.assertIn("factory and deli meats:", rules)
        self.assertIn("Open Food Facts products", rules)
        for word in ("liver", "bologna", "nugget"):
            self.assertIn(word, rules)


class BreakfastRulesTextTests(TestCase):
    def test_rules_describe_the_breakfast_preferences(self):
        rules = vp.build_packet(goals=(2000,), meals=("lunch",)).rules_md
        self.assertIn("canned items not offered in: Viands - Fish & Seafood", rules)
        self.assertIn("canned items not offered in: Rice & Grains, Starchy Roots & Tubers", rules)
        self.assertIn("food groups are mixed", rules)
        self.assertIn("ranked first when the name contains: egg, tofu", rules)
        self.assertNotIn("yoghurt, cheese, milk", rules)  # cheese is not a preferred breakfast food
        self.assertIn("pandesal", rules)
        self.assertIn("at most 340 kcal per 100 g", rules)
        self.assertIn("eggnog", rules)
        self.assertIn("Ingredients, not a portion of food (never suggested)", rules)
        self.assertIn(f"preferred foods (breakfast, section 4): {vp.mb.W_PREFER}", rules)


class RawFoodsOrderTests(TestCase):
    def test_common_names_are_listed_before_uncommon_ones_even_when_the_alphabet_says_otherwise(self):
        make_food("Abalone", "viands_fish", 105, 17, 6, 0.8)          # raw-looking, uncommon: first alphabetically
        make_food("Chicken white meat", "viands_meat", 120, 23, 0, 2.5)  # raw-looking, common name
        names = [r["name"] for r in vp.build_raw_rows()]
        self.assertEqual(names, ["Chicken white meat", "Abalone"])
