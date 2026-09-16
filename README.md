# Fitness Assistant

An AI-powered personalized fitness assistant — a mobile-first Progressive Web App. It combines workout planning, Filipino-food-based nutrition tracking, an LLM chat coach, and automated progress reporting into a single installable app.

## Features

- **Workouts** — Workout templates and exercise history powered by the open-source [wger](https://wger.de/) exercise database, including a "swap exercise" feature for replacing generated exercises in a template.
- **Nutrition** — Daily food logging against a curated, locally-built Filipino food database (1,500+ items sourced from PhilFCT), with:
  - Auto-calculated calorie/macro goals (BMR/TDEE)
  - Category browsing with paginated search
  - Editable log entries (swap food, move to a different day)
  - Weekly/monthly trend views with streaks and macro averages
- **Coach** — An LLM-powered chat assistant (via Groq) with context drawn from the user's real workout, nutrition, and weight-log data.
- **Progress Reports** — On-demand and interval-based reports combining a rule-based analyzer with an LLM-generated narrative summary. Includes:
  - Manual and automatic (interval) generation with due/no-data detection
  - PDF export
  - Per-user report numbering and history
- **Weight Log** — Daily weight entries with a trend graph, feeding into both the coach's context and progress reports.
- **Resources** — A read-only, admin-managed catalog of workout/nutrition articles.
- **PWA support** — Installable, mobile-first, with offline app-shell caching.

## Tech Stack

**Backend:** Django + Django REST Framework
**Frontend:** React (Vite), PWA-enabled
**Exercise data:** wger (open-source, no rate limits)
**Nutrition data:** Self-curated Filipino food database (PhilFCT)
**LLM:** Groq (OpenAI-compatible API, free tier)

## Project Structure

```
Fita/
├── fitness_backend/     # Django + DRF backend
│   ├── accounts/        # Custom email-based auth, profile, weight log
│   ├── workouts/        # Templates, exercises, history (wger-backed)
│   ├── nutrition/       # Filipino food DB, daily logging, trends
│   ├── coach/           # LLM chat assistant + data collection service
│   ├── progress/        # Rule-based analyzer + LLM report generation
│   └── resources/       # Admin-managed article catalog
├── fitness_frontend/    # React (Vite) PWA frontend
├── .gitignore
└── requirements.txt
```

## Getting Started

### Backend

```bash
cd fitness_backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r ../requirements.txt
```

Create a `.env` file in `fitness_backend/` with:

```
GROQ_API_KEY=your_groq_api_key
SECRET_KEY=your_django_secret_key
DEBUG=True
```

Then run migrations and start the server:

```bash
python manage.py migrate
python manage.py runserver
```

### Frontend

```bash
cd fitness_frontend
npm install
npm run dev
```

## Design System

A dark "gym floor" theme — chili red / bamboo green / turmeric gold palette, Archivo Black + Barlow Condensed for display type, IBM Plex Mono for stats.

## License

Not yet specified.