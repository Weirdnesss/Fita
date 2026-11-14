"""Tests for the nutrition validation packet (nutrition/services/goals_packet.py)."""

import csv
import tempfile
from pathlib import Path
from types import SimpleNamespace

from django.core.management import call_command
from django.test import TestCase

from .models import FoodItem
from .services import goal_calculator as gc
from .services import goals_packet as gp


def make_food(name, source="Estimated composite dish", kcal=100, p=5, c=10, f=4):
    return FoodItem.objects.create(
        name=name, category="rice_grains", serving_description="1 serving", serving_size_g=100,
        calories=kcal, protein_g=p, carbs_g=c, fat_g=f, source=source,
    )


class RulesTests(TestCase):
    def test_rules_follow_live_constants(self):
        body, fingerprint = gp.build_rules_md()
        self.assertEqual(len(fingerprint), 12)
        self.assertIn("Mifflin-St Jeor", body)
        self.assertIn(str(gc.BEGINNER_TDEE_FACTOR), body)
        self.assertIn(f"{gc.MIN_SAFE_CALORIES['female']} kcal", body)
        for goal in gc.GOAL_CALORIE_ADJUSTMENT:
            self.assertIn(goal.replace("_", " ").title(), body)

    def test_fingerprint_changes_when_a_rule_changes(self):
        _, before = gp.build_rules_md()
        original = gc.BEGINNER_TDEE_FACTOR
        gc.BEGINNER_TDEE_FACTOR = 0.9
        try:
            _, after = gp.build_rules_md()
        finally:
            gc.BEGINNER_TDEE_FACTOR = original
        self.assertNotEqual(before, after)


class AuditTests(TestCase):
    def profile(self, **kw):
        base = dict(gender="female", age=25, current_weight_kg=60, height_cm=165,
                    activity_level="sedentary", primary_goal="maintain_weight")
        base.update(kw)
        return SimpleNamespace(**base)

    def test_real_results_are_clean(self):
        p = self.profile()
        self.assertEqual(gp.audit_goals(p, gc.calculate_goals(p)), [])

    def test_catches_bad_results(self):
        p = self.profile(current_weight_kg=60)
        bad = SimpleNamespace(calories=900, protein_g=150, carbs_g=0, fat_g=10, tdee=2000, calorie_floor_applied=False)
        text = " ".join(gp.audit_goals(p, bad))
        for expected in ("calorie floor", "deficit larger", "macros add up", "protein above", "carbohydrate target is 0"):
            self.assertIn(expected, text)


class PacketTests(TestCase):
    def test_all_sample_goals_pass_the_audit(self):
        rows = gp.build_sample_rows()
        self.assertEqual(len(rows), 3 * 3 * 3 * 2 * 5)
        self.assertEqual([(r["scenario"], r["flags"]) for r in rows if r["flags"]], [])

    def test_foods_to_check_lists_only_estimated_shared_foods(self):
        make_food("Pritong Isda")
        make_food("Kanin", source="PhilFCT 2023, item 1")
        rows = gp.build_food_rows()
        self.assertEqual([r["name"] for r in rows], ["Pritong Isda"])

    def test_command_writes_every_file(self):
        make_food("Pritong Isda")
        with tempfile.TemporaryDirectory() as tmp:
            call_command("export_nutrition_packet", "--out", tmp)
            for name in ("rules.md", "sample_goals.csv", "foods_to_check.csv", "coach_rules.md", "review_form.md", "summary.md"):
                self.assertTrue((Path(tmp) / name).exists(), name)
            with open(Path(tmp) / "sample_goals.csv", encoding="utf-8-sig") as f:
                self.assertEqual(len(list(csv.DictReader(f))), 270)
            fingerprint = gp.build_rules_md()[1]
            self.assertIn(fingerprint, (Path(tmp) / "review_form.md").read_text(encoding="utf-8"))
