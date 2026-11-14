"""
Review packet for trainer / adviser validation of the workout generator.

Reviewers sign off on RULES and DATA, not on individual outputs. Everything here is read
from the live code, so the documents cannot drift from what the app does:

  rules.md              every rule and number the generator uses, with a fingerprint to
                        cite ("validated rules a1b2c3d4e5f6")
  exercise_pool.csv     every exercise the generator may pick (and the ones its beginner
                        rules block, with the reason), with empty verdict columns to fill in
  sample_routines.csv   routines built for a grid of frequency x goal x location, plus
                        medical-condition cases, with an independent sanity audit (flags)
  coach_rules.md        the coach's system prompt and the pain/injury guard, as shipped
  review_form.md        a sign-off form for the trainer
  summary.md            counts, flags and the fingerprint, on one page

Nothing is written to the database: sample routines are built for a throwaway user inside
a transaction that is always rolled back.
"""

import csv
import hashlib
from dataclasses import dataclass
from pathlib import Path

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from accounts.models import PrimaryGoal, Profile, WorkoutFrequency, WorkoutLocation
from workouts.models import WgerExercise
from workouts.services import workout_generator as wg

FREQUENCIES = (
    WorkoutFrequency.ONE_TO_TWO, WorkoutFrequency.THREE_TO_FOUR,
    WorkoutFrequency.FIVE_TO_SIX, WorkoutFrequency.DAILY,
)
GOALS = (
    PrimaryGoal.LOSE_WEIGHT, PrimaryGoal.GAIN_MUSCLE, PrimaryGoal.MAINTAIN_WEIGHT,
    PrimaryGoal.BUILD_STRENGTH, PrimaryGoal.GAIN_WEIGHT,
)
LOCATIONS = (WorkoutLocation.GYM, WorkoutLocation.HOME, WorkoutLocation.MIXED)
# Medical-condition cases: each recognised keyword, plus one the generator cannot act on.
CONDITION_CASES = ("knee", "hip", "ankle", "shoulder", "back", "lower back", "neck", "wrist", "asthma")

SAMPLE_COLUMNS = [
    "scenario", "frequency", "goal", "location", "medical_conditions", "routine", "order",
    "exercise", "category", "equipment", "target_sets", "logged_as", "flags",
]
POOL_COLUMNS = [
    "category", "location", "status", "id", "name", "equipment", "muscles",
    "reviewer_verdict (ok / change / remove)", "reviewer_notes",
]


@dataclass
class Packet:
    rules_md: str
    fingerprint: str
    sample_rows: list
    pool_rows: list
    coach_md: str
    form_md: str
    summary_md: str
    stats: dict


# --------------------------------------------------------------------------- rules

def _list(items):
    return ", ".join(f'"{i}"' for i in items)


def build_rules_md():
    """Returns (markdown, fingerprint). The fingerprint covers the rules only, not the date."""
    lines = []
    add = lines.append
    add("# Workout generator: rules for trainer review")
    add("")
    add("Every value below is read from the running code. The generator is rule-based; no language model takes part in choosing exercises, sets, or splits.")
    add("")
    add("## 1. Who it is for")
    add("Every account is treated as a gym beginner. The beginner rules below always apply, whatever the goal.")
    add("")
    add("## 2. Split chosen from the user's workout frequency")
    add("| Days per week | Routines generated |")
    add("|---|---|")
    labels = wg.DAY_TYPE_LABELS
    for freq in FREQUENCIES:
        add(f"| {freq.label} | {', '.join(labels[d] for d in wg.SPLITS[freq])} |")
    add("")
    add("## 3. Muscle categories trained per routine")
    add("| Routine | Categories |")
    add("|---|---|")
    for day, cats in wg.DAY_TYPE_CATEGORIES.items():
        add(f"| {labels[day]} | {', '.join(cats)} |")
    add("")
    add("Note: the exercise source does not separate biceps from triceps inside Arms, so Push and Pull both draw from the same Arms pool.")
    add("")
    add("## 4. Volume")
    add("| Goal | Exercises per category | Sets per exercise |")
    add("|---|---|---|")
    for goal in GOALS:
        n, s = wg.GOAL_PARAMS.get(goal, wg.DEFAULT_GOAL_PARAMS)
        add(f"| {goal.label} | {n} | {min(s, wg.MAX_SETS)} |")
    add("")
    add(f"Sets per exercise are capped at {wg.MAX_SETS} for every goal, so novices learn movement patterns on low volume. The generator sets the number of sets only; it does not prescribe reps or loads.")
    add("")
    add("## 5. Which exercises can be picked (beginner safety)")
    add("An exercise is allowed only if all of these hold:")
    add("1. Its name matches a well-known staple for its category (list in section 6).")
    add(f"2. Its name does not contain a blocked word: {_list(wg.BEGINNER_EXCLUDE_KEYWORDS)}.")
    add('3. Its equipment does not include a barbell.')
    add(f"4. For a home workout, its equipment is one of: {_list(wg.HOME_EQUIPMENT)}. (\"Gym\" and \"Mixed\" have no equipment limit apart from rule 3.)")
    add("")
    add("There are no fallbacks: if a category has no allowed exercise, it yields nothing rather than relaxing a rule. A routine with no exercises is not created. The same rules apply to generating, swapping an exercise, adding one to a generated routine, and the suggest button.")
    add("")
    add("## 6. Staple exercises per category (matched by name keyword)")
    add("| Category | Keywords |")
    add("|---|---|")
    for cat, kws in wg.COMMON_EXERCISE_KEYWORDS.items():
        add(f"| {cat} | {_list(kws)} |")
    add("")
    add("## 7. Medical conditions and injuries (coarse safety net)")
    add("The profile's free-text medical conditions are searched for these words. A match drops whole categories, and some words also block named exercises.")
    add("")
    add("| Word found | Categories dropped | Exercise names blocked |")
    add("|---|---|---|")
    keys = sorted(set(wg.CONDITION_EXCLUDED_CATEGORIES) | set(wg.CONDITION_EXCLUDED_EXERCISE_KEYWORDS))
    for k in keys:
        cats = ", ".join(wg.CONDITION_EXCLUDED_CATEGORIES.get(k, [])) or "none"
        names = ", ".join(wg.CONDITION_EXCLUDED_EXERCISE_KEYWORDS.get(k, [])) or "none"
        add(f"| {k} | {cats} | {names} |")
    add("")
    add("This is not medical advice and does not judge which specific exercises are safe for a condition. Whenever any medical condition is on file, the app shows a notice that the routine should be reviewed with a doctor or physical therapist. Two versions exist: one when a word above matched (it names the categories avoided), and one when none matched (it says the app has no specific guidance).")
    add("")
    add("## 8. How each exercise is logged")
    add("Decided once, when an exercise is added, in this order:")
    add(f"1. Loaded equipment ({_list(sorted(wg.LOADED_EQUIPMENT))}): weight x reps.")
    add(f"2. Name contains {_list(wg.TIME_EXERCISE_KEYWORDS)}, or category is Cardio: time.")
    add(f"3. Name contains {_list(wg.WEIGHTED_NAME_KEYWORDS)}: weight x reps.")
    add(f"4. Name contains {_list(wg.REPS_ONLY_NAME_KEYWORDS)}: reps only.")
    add(f"5. Only bodyweight equipment ({_list(sorted(wg.BODYWEIGHT_EQUIPMENT))}): reps only.")
    add("6. Otherwise: weight x reps. Users can change this later.")
    add("")
    add("## 9. When Generate is available")
    add("Generate creates or refreshes every routine in the split at once. It is offered only the first time, after the user changes goal, frequency, or location, or when a routine in the split is missing. Otherwise existing exercises are left alone so a beginner keeps practising what is in the plan. The same profile always produces the same plan.")
    body = "\n".join(lines)
    fingerprint = hashlib.sha256(body.encode()).hexdigest()[:12]
    return body, fingerprint


# --------------------------------------------------------------------------- exercise pool

def _block_reason(ex, category, location):
    """Why a staple-matching exercise is NOT allowed, or '' if it is allowed (mirrors the generator)."""
    if wg._name_has_keyword(ex.name, wg.BEGINNER_EXCLUDE_KEYWORDS):
        return "blocked word in name (technical or advanced movement)"
    equipment = (ex.equipment_name or "").lower()
    if "barbell" in equipment:
        return "uses a barbell"
    if location == WorkoutLocation.HOME and not any(h in equipment for h in wg.HOME_EQUIPMENT):
        return "needs gym equipment (not available at home)"
    return ""


def build_pool_rows():
    rows = []
    for category, staples in wg.COMMON_EXERCISE_KEYWORDS.items():
        exercises = list(WgerExercise.objects.filter(category_name__iexact=category).order_by("id"))
        for location in (WorkoutLocation.GYM, WorkoutLocation.HOME):
            for ex in exercises:
                if not wg._name_has_keyword(ex.name, staples):
                    continue
                reason = _block_reason(ex, category, location)
                rows.append({
                    "category": category, "location": location.label,
                    "status": "excluded: " + reason if reason else "allowed",
                    "id": ex.id, "name": ex.name, "equipment": ex.equipment_name,
                    "muscles": ex.muscle_names,
                })
    return rows


# --------------------------------------------------------------------------- audit

def audit_routine(rows, location, condition_text=""):
    """
    Independent sanity checks on one routine's exercises (a list of dicts with name, category,
    equipment, target_sets). Returns a list of flag strings; empty means nothing found.
    Deliberately written without calling the generator's own filters.
    """
    flags = []
    if not rows:
        return ["routine has no exercises"]
    seen = set()
    text = (condition_text or "").lower()
    for r in rows:
        name = r["name"].lower()
        equipment = (r["equipment"] or "").lower()
        if "barbell" in equipment:
            flags.append(f"barbell exercise: {r['name']}")
        for word in wg.BEGINNER_EXCLUDE_KEYWORDS:
            if word in name:
                flags.append(f"blocked word '{word}' in {r['name']}")
                break
        if r["target_sets"] > wg.MAX_SETS:
            flags.append(f"{r['target_sets']} sets (cap is {wg.MAX_SETS}): {r['name']}")
        if location == WorkoutLocation.HOME and not any(h in equipment for h in wg.HOME_EQUIPMENT):
            flags.append(f"needs gym equipment at home: {r['name']}")
        key = r["name"]
        if key in seen:
            flags.append(f"duplicate exercise: {r['name']}")
        seen.add(key)
        for word, cats in wg.CONDITION_EXCLUDED_CATEGORIES.items():
            if word in text and r["category"] in cats:
                flags.append(f"{r['category']} exercise despite '{word}' on file: {r['name']}")
    return flags


# --------------------------------------------------------------------------- sample routines

def _scenarios():
    for freq in FREQUENCIES:
        for goal in GOALS:
            for loc in LOCATIONS:
                yield freq, goal, loc, ""
    for cond in CONDITION_CASES:
        yield WorkoutFrequency.FIVE_TO_SIX, PrimaryGoal.GAIN_MUSCLE, WorkoutLocation.GYM, cond


def build_sample_rows():
    """Builds routines for each scenario for a throwaway user; the transaction is always rolled back."""
    Account = get_user_model()
    rows = []
    if not WgerExercise.objects.exists():
        return rows
    for i, (freq, goal, loc, cond) in enumerate(_scenarios(), start=1):
        with transaction.atomic():
            user = Account.objects.create_user(email=f"packet-{i}@example.invalid", password="x-packet-only")
            Profile.objects.update_or_create(user=user, defaults={
                "workout_frequency": freq, "primary_goal": goal, "workout_location": loc,
                "medical_conditions": cond,
            })
            label = f"{freq.label} | {goal.label} | {loc.label}" + (f" | condition: {cond}" if cond else "")
            try:
                templates = wg.generate_workout(user, seed=f"packet|{freq}|{goal}|{loc}|{cond}")
            except wg.WorkoutGeneratorError as exc:
                rows.append({
                    "scenario": label, "frequency": freq.label, "goal": goal.label, "location": loc.label,
                    "medical_conditions": cond, "routine": "(none)", "order": "", "exercise": "",
                    "category": "", "equipment": "", "target_sets": "", "logged_as": "",
                    "flags": f"generator refused: {exc}",
                })
                transaction.set_rollback(True)
                continue
            for t in templates:
                ex_rows = [
                    {"name": e.exercise_name, "category": e.category_name,
                     "equipment": e.equipment_name, "target_sets": e.target_sets}
                    for e in t.exercises.all()
                ]
                flags = audit_routine(ex_rows, loc, cond)
                for e in t.exercises.all():
                    rows.append({
                        "scenario": label, "frequency": freq.label, "goal": goal.label,
                        "location": loc.label, "medical_conditions": cond, "routine": t.title,
                        "order": e.order + 1, "exercise": e.exercise_name, "category": e.category_name,
                        "equipment": e.equipment_name, "target_sets": e.target_sets,
                        "logged_as": e.get_input_type_display(), "flags": "; ".join(flags),
                    })
            transaction.set_rollback(True)
    return rows


# --------------------------------------------------------------------------- coach, form, summary

def build_coach_md():
    from coach.services import llm_service
    lines = ["# Coach chat: safety rules as shipped", ""]
    lines.append("The coach is the one free-form use of the language model. These are its rules, read from the files in use.")
    lines += ["", "## System prompt", "", "```text"]
    try:
        lines.append(Path(llm_service.PROMPT_FILE).read_text(encoding="utf-8").strip())
    except OSError:
        lines.append("(prompt file not found)")
    lines.append("```")
    try:
        from coach.services import pain_guard
    except ImportError:
        pain_guard = None
    lines += ["", "## Pain and injury guard (rule in code)", ""]
    if pain_guard is None:
        lines.append("Not installed in this version.")
    else:
        lines.append("If a message mentions pain, stiffness, or a possible injury, the reply is forced into a short fixed form and the Detailed setting is ignored for that message.")
        lines += ["", "```text", pain_guard.PAIN_SYSTEM_BLOCK, "```"]
    return "\n".join(lines) + "\n"


def build_form_md(fingerprint):
    return f"""# Trainer review form

Rules fingerprint: `{fingerprint}` (cite this when you sign; it changes whenever a rule changes)

Reviewer name: ____________________  Credentials / certification: ____________________

Date: ____________________  Years coaching beginners: ____________________

Mark each statement: Agree / Agree with changes / Disagree. Add notes where you do not fully agree.

| # | Statement | Verdict | Notes |
|---|---|---|---|
| 1 | The split by days per week (1-2 full body; 3-4 upper/lower; 5-6 or daily push/pull/legs) suits gym beginners. | | |
| 2 | The muscle categories trained in each routine are appropriate. | | |
| 3 | At most 3 sets per exercise, and 1 or 2 exercises per category, is an appropriate volume for beginners. | | |
| 4 | The blocked-movement list covers what beginners should not do unsupervised. | | |
| 5 | Excluding barbell exercises is appropriate for beginners. | | |
| 6 | The home-equipment list is realistic. | | |
| 7 | The exercises marked "allowed" in exercise_pool.csv are acceptable (record exceptions in that file). | | |
| 8 | The sample routines are safe and sensible for beginners (see flags column). | | |
| 9 | The medical-condition rules are a reasonable minimum, and the notice to see a doctor or physical therapist is sufficient. | | |
| 10 | The coach's safety rules (coach_rules.md) are appropriate for beginners. | | |

Anything missing or unsafe that you would change: ______________________________________________

Signature: ____________________
"""


def _summary(fingerprint, sample_rows, pool_rows, stats):
    flagged = stats["flagged_routines"]
    lines = [
        "# Workout packet: summary", "",
        f"Generated {timezone.now():%Y-%m-%d %H:%M}.", "",
        f"**Rules fingerprint: `{fingerprint}`** (changes whenever any rule or number in rules.md changes)", "",
        "## Counts", "",
        f"- Scenarios built: {stats['scenarios']} ({stats['routines']} routines, {stats['sample_exercises']} exercise rows)",
        f"- Routines with a flag: {flagged}",
        f"- Exercises in the pool listing: {stats['pool_total']} ({stats['pool_allowed']} allowed, {stats['pool_excluded']} excluded by a beginner rule)",
        f"- Exercise database rows: {stats['db_exercises']}", "",
    ]
    if flagged:
        lines += ["## Flags to look at", ""]
        seen = set()
        for r in sample_rows:
            if r["flags"] and (r["scenario"], r["routine"]) not in seen:
                seen.add((r["scenario"], r["routine"]))
                lines.append(f"- {r['scenario']} / {r['routine']}: {r['flags']}")
    else:
        lines.append("No routine was flagged by the audit.")
    lines += ["", "## Files", "",
              "- rules.md: what the generator does", "- exercise_pool.csv: every exercise it may pick, with verdict columns",
              "- sample_routines.csv: example routines and flags", "- coach_rules.md: the chat coach's safety rules",
              "- review_form.md: sign-off form"]
    return "\n".join(lines) + "\n"


def build_packet():
    rules_body, fingerprint = build_rules_md()
    rules_md = rules_body + f"\n\n---\n**Rules fingerprint: `{fingerprint}`**\n"
    sample_rows = build_sample_rows()
    pool_rows = build_pool_rows()
    routines = {(r["scenario"], r["routine"]) for r in sample_rows if r["routine"] != "(none)"}
    flagged = {(r["scenario"], r["routine"]) for r in sample_rows if r["flags"]}
    stats = {
        "scenarios": len({r["scenario"] for r in sample_rows}),
        "routines": len(routines),
        "sample_exercises": sum(1 for r in sample_rows if r["exercise"]),
        "flagged_routines": len(flagged),
        "pool_total": len(pool_rows),
        "pool_allowed": sum(1 for r in pool_rows if r["status"] == "allowed"),
        "pool_excluded": sum(1 for r in pool_rows if r["status"] != "allowed"),
        "db_exercises": WgerExercise.objects.count(),
    }
    return Packet(rules_md, fingerprint, sample_rows, pool_rows, build_coach_md(),
                  build_form_md(fingerprint), _summary(fingerprint, sample_rows, pool_rows, stats), stats)


def write_packet(packet, out_dir):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "rules.md").write_text(packet.rules_md, encoding="utf-8")
    (out / "coach_rules.md").write_text(packet.coach_md, encoding="utf-8")
    (out / "review_form.md").write_text(packet.form_md, encoding="utf-8")
    (out / "summary.md").write_text(packet.summary_md, encoding="utf-8")
    # utf-8-sig so Excel opens the files correctly
    for name, cols, rows in (("sample_routines.csv", SAMPLE_COLUMNS, packet.sample_rows),
                             ("exercise_pool.csv", POOL_COLUMNS, packet.pool_rows)):
        with open(out / name, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
    return out
