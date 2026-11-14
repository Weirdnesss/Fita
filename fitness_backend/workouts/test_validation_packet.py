"""
Tests for the trainer validation packet (workouts/services/validation_packet.py and
`manage.py export_workout_packet`): rules must follow the live constants, building the packet
must never write to the database, and the audit must catch problems.
"""

import csv
import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from accounts.models import WorkoutLocation
from .models import WgerExercise, WorkoutTemplate
from .services import validation_packet as vp
from .services import workout_generator as wg

Account = get_user_model()

STAPLES = {
    "Chest": [("Dumbbell Bench Press", "Dumbbell"), ("Push-Ups", "none (bodyweight exercise)"),
              ("Barbell Bench Press", "Barbell, Bench"), ("Chest Press Machine", "Machine")],
    "Back": [("Lat Pulldown", "Cable"), ("Seated Row", "Machine"), ("Bent Over Row", "Barbell")],
    "Legs": [("Squats", "none (bodyweight exercise)"), ("Leg Press", "Machine"), ("Jump Squat", "none (bodyweight exercise)"),
             ("Goblet Squat", "Kettlebell"), ("Lunges", "Dumbbell")],
    "Shoulders": [("Shoulder Press", "Dumbbell"), ("Lateral Raises", "Dumbbell"), ("Upright Row", "Barbell")],
    "Arms": [("Bicep Curls", "Dumbbell"), ("Tricep Pushdown", "Cable"), ("Hammer Curls", "Dumbbell")],
    "Abs": [("Plank", "none (bodyweight exercise)"), ("Crunches", "gym mat"), ("Leg Raises", "gym mat")],
    "Calves": [("Calf Raises", "none (bodyweight exercise)"), ("Standing Calf Raise Machine", "Machine calf raise")],
}


def seed_exercises():
    i = 1
    for cat, items in STAPLES.items():
        for name, eq in items:
            WgerExercise.objects.create(id=i, name=name, category_name=cat, equipment_name=eq)
            i += 1


class RulesTests(TestCase):
    def test_rules_follow_live_constants(self):
        body, fingerprint = vp.build_rules_md()
        self.assertEqual(len(fingerprint), 12)
        for day_label in ("Full Body", "Upper Body", "Lower Body", "Push", "Pull", "Legs"):
            self.assertIn(day_label, body)
        for word in wg.BEGINNER_EXCLUDE_KEYWORDS:
            self.assertIn(f'"{word}"', body)
        self.assertIn(f"capped at {wg.MAX_SETS}", body)

    def test_fingerprint_changes_when_a_rule_changes(self):
        _, before = vp.build_rules_md()
        original = wg.MAX_SETS
        wg.MAX_SETS = 4
        try:
            _, after = vp.build_rules_md()
        finally:
            wg.MAX_SETS = original
        self.assertNotEqual(before, after)

    def test_fingerprint_is_stable(self):
        self.assertEqual(vp.build_rules_md()[1], vp.build_rules_md()[1])


class AuditTests(TestCase):
    def row(self, **kw):
        base = {"name": "Leg Press", "category": "Legs", "equipment": "Machine", "target_sets": 3}
        base.update(kw)
        return base

    def test_clean_routine_has_no_flags(self):
        self.assertEqual(vp.audit_routine([self.row()], WorkoutLocation.GYM), [])

    def test_empty_routine_is_flagged(self):
        self.assertTrue(vp.audit_routine([], WorkoutLocation.GYM))

    def test_barbell_blocked_word_sets_and_duplicates_are_caught(self):
        flags = vp.audit_routine([
            self.row(name="Power Clean", equipment="Barbell"),
            self.row(target_sets=5),
            self.row(target_sets=5),
        ], WorkoutLocation.GYM)
        text = " ".join(flags)
        for expected in ("barbell", "blocked word", "sets (cap", "duplicate"):
            self.assertIn(expected, text)

    def test_gym_equipment_at_home_is_caught(self):
        self.assertTrue(vp.audit_routine([self.row()], WorkoutLocation.HOME))

    def test_excluded_category_for_condition_is_caught(self):
        flags = vp.audit_routine([self.row()], WorkoutLocation.GYM, "bad knee")
        self.assertTrue(any("knee" in f for f in flags))


class PacketTests(TestCase):
    def setUp(self):
        seed_exercises()

    def test_pool_lists_allowed_and_excluded_with_reasons(self):
        rows = vp.build_pool_rows()
        by = {(r["name"], r["location"]): r["status"] for r in rows}
        self.assertEqual(by[("Squats", "Gym")], "allowed")
        self.assertIn("barbell", by[("Barbell Bench Press", "Gym")])
        self.assertIn("blocked word", by[("Jump Squat", "Gym")])
        self.assertIn("gym equipment", by[("Leg Press", "Home")])

    def test_sample_routines_pass_the_audit_and_leave_no_data(self):
        accounts_before = Account.objects.count()
        rows = vp.build_sample_rows()
        self.assertTrue(rows)
        self.assertEqual([r for r in rows if r["flags"] and "refused" not in r["flags"]], [])
        self.assertEqual(Account.objects.count(), accounts_before)
        self.assertEqual(WorkoutTemplate.objects.count(), 0)

    def test_knee_case_has_no_legs_exercise(self):
        rows = [r for r in vp.build_sample_rows() if r["medical_conditions"] == "knee" and r["exercise"]]
        self.assertTrue(rows)
        self.assertNotIn("Legs", {r["category"] for r in rows})

    def test_command_writes_every_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            call_command("export_workout_packet", "--out", tmp)
            for name in ("rules.md", "exercise_pool.csv", "sample_routines.csv",
                         "coach_rules.md", "review_form.md", "summary.md"):
                self.assertTrue((Path(tmp) / name).exists(), name)
            with open(Path(tmp) / "sample_routines.csv", encoding="utf-8-sig") as f:
                self.assertTrue(list(csv.DictReader(f)))
