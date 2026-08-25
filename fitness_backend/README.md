<<<<<<< HEAD
# PrimeFit Backend (Accounts module)

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
main improvement over the original's US-centric free-tier API.

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

Note on scheduling: the original thesis used Celery + django-celery-beat
for automatic midnight generation. This build uses on-demand generation
(a button/API call) instead -- simpler to run and demo without a task
queue. ProgressReportSettings.next_generation_date() is still there if
you want to add a scheduler (Celery, django-crontab, or even a simple
management command + cron) later.

Uses the same GROQ_API_KEY as the coach app. If it's missing, /generate/
returns 502 immediately (before touching the database) rather than
silently failing partway through.
=======
# Fitness-Assistant
>>>>>>> a944bdbe0b8d682cecf72f064beb8dc24699916e
