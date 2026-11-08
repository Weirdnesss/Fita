# Fitness Assistant Backend (Accounts module)

## Setup
```
python -m venv venv
source venv/bin/activate   # on Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py createsuperuser   # optional, for /admin/
python manage.py runserver
```

## Endpoints (all under /accounts/)
- POST   /register/        -- Sign Up Step 1 (email, first_name, last_name, password, confirm_password)
- POST   /login/           -- returns {access, refresh} JWT tokens
- POST   /login/refresh/   -- refresh an access token
- GET    /profile/         -- get own profile
- PATCH  /profile/         -- Sign Up Steps 2 & 3 / Edit Profile (gender, activity_level, current_weight_kg, goal_weight_kg, height_ft, height_in, primary_goal, medical_conditions, food_allergies, workout_frequency, workout_location)
- GET    /me/              -- full account + nested profile (for Profile page)

## Auth
Send `Authorization: Bearer <access_token>` on protected endpoints.

## Workouts module (/workouts/)
- GET  /exercises/search/?q=bench       -- searches the LOCAL exercise cache (see below)
- GET  /templates/                       -- list your routines
- POST /templates/                       -- create a routine {"title", "kind": "main"|"alternative"}
- GET/PATCH/DELETE /templates/<id>/
- POST /templates/<id>/exercises/        -- add an exercise {"wger_exercise_id", "target_sets"}
- GET  /history/                         -- past completed sessions
- POST /history/                         -- log a finished session:
  {"template_title", "started_at", "exercises": [{"exercise_name", "sets_data": [{"weight", "reps"}]}]}

**Exercise data setup (do this first)**: exercise search/add now reads from
a LOCAL cache (WgerExercise model), not a live call to wger.de. wger's
undocumented internal search endpoint (`/exercise/search/`) returned a
plain 404 in real-world testing -- it's internal-only tooling per wger's
own GitHub issue #329 and isn't guaranteed to exist. Caching locally is
more robust and also means search works offline once synced, which fits
a PWA better anyway.

Run once after setup (needs internet, takes a few minutes for ~800+ exercises):
```
python manage.py sync_wger_exercises
```
Use `--limit 50` for a quick test sync. Re-run periodically (e.g. monthly)
to pick up new exercises from wger. If search returns an empty cache hint,
you haven't synced yet.

`/exerciseinfo/` returns heavily nested data per exercise, so it can be
slow -- the sync command uses a 30s timeout, 25-per-page requests, and
retries up to 3x on timeouts (with backoff) by default. If you still see
timeouts on your connection, try:
```
python manage.py sync_wger_exercises --page-size 10 --timeout 60
```
Progress is saved incrementally (each exercise is upserted as it's
fetched), so re-running the command after a partial failure just updates
existing entries rather than duplicating or losing progress.

**Diagnostics**: `python manage.py test_wger "search term"` hits wger.de
directly and prints the raw response -- useful for checking connectivity
or if wger changes their API shape again, independent of the sync command.

## Nutrition module (/nutrition/)
Uses a **local Filipino food database** (FoodItem model) instead of an
external API -- no rate limits, works offline, and is the thesis's
main improvement over a typical US-centric free-tier API.

- GET   /foods/search/?q=adobo&category=viands_meat   -- search local DB
- GET   /profile/                                       -- daily macro goals
- PATCH /profile/                                       -- update goals
- GET   /daily/?date=2026-08-22                          -- today's log if no date given
- POST  /entries/                                        -- log food: {"food_item", "meal_type", "servings", "date"}
- DELETE /entries/<id>/

**Seed data**: run `python manage.py seed_foods` after migrating to load ~46
starter Filipino dishes. IMPORTANT -- these values are reasonable estimates,
NOT transcribed from PhilFCT (no public bulk dataset exists; PhilFCT is a
web lookup tool at https://i.fnri.dost.gov.ph/fct/library, and bulk data
requires an FOI request to FNRI). Before using these numbers in your thesis
Results, cross-check each item against PhilFCT's online lookup or your FOI
response and update the `source` field. Add new foods either through
/admin/ or by extending nutrition/management/commands/seed_foods.py.

### More food data + meal suggestions
PhilFCT doesn't cover every common food, so the database also takes data from
other sources. Every row records where it came from (`source`, `external_id`),
search ranks PhilFCT first, and the API returns `source_type` / `source_label`
(`philfct`, `usda`, `openfoodfacts`, `user`, `estimated`).

- `python manage.py import_usda --dir <unzipped FDC folder> [--dir ...] [--skip-existing-names] [--dry-run]`
  -- USDA FoodData Central (public domain). Download the SR Legacy and
  Foundation Foods CSVs from https://fdc.nal.usda.gov/download-datasets.
- `python manage.py import_openfoodfacts [--max-pages 10]` -- Philippine
  packaged products from Open Food Facts (ODbL; keep attribution). Rate
  limited to roughly one request per 7 s by default.
- POST   /foods/custom/ -- a user adds a missing food (private to them),
  PATCH/DELETE /foods/custom/<id>/ to edit it (delete refused once logged)
- GET    /suggestions/?meal_type=lunch&date=2026-10-19&limit=4&explain=true&exclude=12,40
  (`exclude` = food ids already shown, for "show different ideas")
  -- foods that fit what's left of today's goals. Candidates and portions are
  chosen by rule from the database; the LLM (optional, Groq) only picks among
  them by id and words the reason, and any failure falls back to rule-based
  reasons (`reason_source`: "ai" | "rule"). Log a suggestion with the normal
  POST /entries/ using its `food.id` and `servings`. Portions are capped per
  food category (e.g. 150 g for meat/fish) so a suggestion looks like a real serving.
  The React screens are `FoodSuggestions.jsx` (Meal Ideas) and `CustomFoodForm.jsx`.
- GET    /suggestions/meals/?meal_type=lunch&date=2026-10-19&limit=3&explain=true&exclude=12,40
  -- whole plates (a protein plus a carb and a vegetable or fruit, 2-3 foods)
  sized to what's left today. Same hybrid rule: plates are built by rule
  (`nutrition/services/meal_builder.py`); the LLM only picks plates by index and
  words the reason. Response: `meals: [{items: [{food, role, servings,
  amount_label, calories, ...}], totals, reason, reason_source}]`. `exclude`
  skips plates whose main food was already shown.
- POST   /entries/bulk/ `{meal_type, date, items: [{food_item, servings}]}`
  -- logs a whole plate atomically (all or nothing, max 10 items). Foods
  created by other users are refused (same visibility rule as /entries/).

## Fitness Assistant module (/coach/)
Uses Groq's free-tier, OpenAI-compatible LLM API (openai/gpt-oss-120b
by default -- Groq's recommended replacement for the now-deprecated
llama-3.3-70b-versatile, see https://console.groq.com/docs/deprecations).

Note: gpt-oss-120b is a reasoning model -- it spends part of its token
budget on internal chain-of-thought before writing the visible reply.
`reasoning_effort="low"` and a generous `max_completion_tokens` (1536
for chat) are set to avoid truncation; if you still see cut-off
responses, raise max_completion_tokens further in
coach/services/llm_service.py (the model supports up to 131K tokens). Get a free key at https://console.groq.com -- no credit card
needed. Add it to your .env as GROQ_API_KEY.

- GET  /chats/                        -- "Previous Chats" list
- POST /chats/                        -- "+ New Chat" button
- GET/DELETE /chats/<id>/             -- open or delete a chat (with messages)
- POST /chats/<id>/messages/          -- send a message: {"content": "..."}
  Returns {"user_message", "assistant_message", "message_id"}.
  First message in a chat also becomes its title.

The assistant is context-aware: it pulls the user's profile, recent
workout history, and recent nutrition into its system prompt on every
call (coach/services/data_collection_service.py), so responses are
personalized without you needing to pass that context from the frontend.

Safety rules (no extreme diets/exercises, defer to professionals for
medical concerns, etc.) live in coach/prompts/system_prompt.txt --
edit that file to adjust the assistant's behavior/scope.

If GROQ_API_KEY is missing or the API call fails, /messages/ returns a
502 with an error message rather than crashing -- your frontend should
handle this (e.g. "Assistant is temporarily unavailable, try again").

To switch providers later (e.g. to OpenAI), only coach/services/llm_service.py
needs to change: swap GROQ_BASE_URL/GROQ_MODEL env vars, or point base_url
at "https://api.openai.com/v1" with an OpenAI key and model name.

## Progress Reports module (/progress/)
The hybrid rule-based + LLM report generator -- the centerpiece module.
Pipeline: structured data collection -> RuleBasedAnalyzer (threshold
rules on real numbers) -> LLM narrative (constrained to JSON output,
grounded in the rule-based insights rather than inventing feedback).

- GET  /reports/                    -- "Generated Reports" list
- GET  /reports/<id>/               -- full report, including rule_based_insights
  (kept alongside the narrative so the hybrid pipeline is inspectable --
  useful for thesis screenshots showing "rules in, narrative out")
- POST /reports/generate/           -- trigger generation now
  Body (optional): {"period_days": 7, "report_type": "short"|"detailed"}
  Defaults to your ProgressReportSettings.
- GET/PATCH /settings/              -- day_interval, report_type, is_enabled

Note on scheduling: this build uses on-demand generation (a button/API
call) instead of automatic midnight generation -- simpler to run and
demo without a task queue. ProgressReportSettings.next_generation_date()
is still there if you want to add a scheduler (Celery, django-crontab,
or even a simple management command + cron) later.

Uses the same GROQ_API_KEY as the coach app. If it's missing, /generate/
returns 502 immediately (before touching the database) rather than
silently failing partway through.

## Resources module (/resources/)
A curated, admin-managed catalog of workout/nutrition articles -- global
and read-only from the API (not scoped per-user, everyone sees the same
list). Populate entries via /admin/.

- GET /resources/?category=workout&q=beginner   -- list, with optional
  category ("workout"|"nutrition"|"general") and title-search filters

### Validation packet for expert review

Reviewers sign off on the rules and the data, not on each suggestion. This command writes
everything they need, generated from the live code so it cannot drift from what the app does:

    python manage.py export_validation_packet              # writes ./validation_packet/
    python manage.py export_validation_packet --out review # or pick a folder

- `rules.md`: every rule and number behind the suggestions, with a **rules fingerprint**
  (cite it as "validated rules <fingerprint>"; it changes whenever any rule or number changes).
  It includes the **common-foods list** (section 9): suggestions are ranked towards foods people
  here actually eat (chicken, tilapia, rice, kangkong...) and away from rare ingredients and
  high-sodium dried/salted fish; balut, ant eggs and powders/canned items are never suggested.
  Deli and factory meats (bologna, nuggets, fish balls) and organ meats (liver, tripe, blood) are
  ranked lower and never boosted, but not banned; these are judgment calls for the reviewer.
  The list lives in `nutrition/services/staples.py`; edit it there and regenerate.
  Breakfast plates rank eggs, tofu, yogurt, milk, tapa/tocino/longganisa and pandesal, bread, oats,
  rice, camote and corn first, never offer canned fish or canned corn/starch, allow up to 340 kcal
  per 100 g for the carb (bread), and mix food groups so one group (dozens of USDA cheeses) cannot
  take every slot: at most `limit // 3` plates share a main-item group (a preference, filled up if
  the database is thin). The lists are the `prefer` fields of `BREAKFAST_PROTEIN` /
  `BREAKFAST_CARB` in `nutrition/services/meal_builder.py`; rules.md section 4 prints them.
- `estimated_foods.csv`: foods that cite no published table (PhilFCT, USDA or Open Food Facts),
  most-used-in-plates first, with empty verdict columns for the reviewer.
- `sample_plates.csv`: plates for 5 calorie goals x 4 meals, each audited independently
  (`flags` column: too small for the meal, over the calories left, over a plate portion
  limit, calories that don't match the macros, a food not on the common-foods list; the
  `common_food` column says yes/no per food).
- `raw_looking_foods.csv`: foods left out of suggestions because their name does not say how
  they were prepared. PhilFCT lists raw foods under plain names ("Tilapia", "Chicken white
  meat", "Potato"), and raw chicken or pork must never be suggested. Scan it for anything that is
  actually cooked and was dropped by mistake (common-sounding names are listed first). Foods whose
  name literally says raw or uncooked are not listed (summary.md gives their count), and Open Food
  Facts products are never treated as raw because they are packaged retail items.
- `summary.md`: counts, flags and the fingerprint on one page.

Run it on the database you actually ship (after the imports), not on a test database. It
writes nothing to the database (sample plates are built for a throwaway user and rolled back).
After changing any rule, rerun it: a different fingerprint means the earlier sign-off no
longer applies to the new rules.

## Testing
Each app has a `tests.py` covering auth requirements, cross-user data
isolation (the property that matters most -- every queryset is scoped to
`request.user`), core CRUD flows, and the missing-GROQ_API_KEY error path
for the two LLM-backed modules (coach, progress).

Run the full suite:
```
python manage.py test
```

Run a single app or test:
```
python manage.py test accounts
python manage.py test accounts.tests.WeightLogTests.test_rejects_implausible_weight
```

No GROQ_API_KEY or internet access is needed to run the tests -- the LLM
integration paths are tested via their config-error behavior (missing key
-> clean 502), not by making real API calls.