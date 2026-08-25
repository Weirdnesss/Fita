# PrimeFit Frontend

React + Vite PWA-style frontend for the PrimeFit fitness assistant.
Mobile-first (max-width 480px), dark gym-floor design system, bottom
tab navigation.

## Setup

```
npm install
cp .env.example .env
npm run dev
```

Runs on http://localhost:5173 by default. Make sure the Django backend
is running on http://127.0.0.1:8000 (or update VITE_API_BASE_URL in
.env to point elsewhere).

## Structure

- `src/api/` — one file per backend module (accounts, workouts, nutrition,
  coach, progress), each a thin wrapper around the matching Django app.
- `src/api/client.js` — shared Axios instance with JWT auth + automatic
  token refresh on 401.
- `src/context/AuthContext.jsx` — current user state, login/logout,
  used by `RequireAuth` to protect routes.
- `src/pages/` — one folder per module, mirroring the backend.
- `src/styles/tokens.css` — the full design system (colors, type,
  component primitives like `.card`, `.btn`, `.pill`, `.stat`).
- `src/App.jsx` — all routes in one place.

## Design system

Dark palette drawn from a Filipino spice rack / gym floor rather than
a generic fitness gradient:
- `--chili` (#e8491d) — primary accent, CTAs
- `--bamboo` (#4c9a6a) — success/positive stats
- `--turmeric` (#d9a441) — warnings/secondary accent
- Display type: Archivo Black / Barlow Condensed (headers)
- Stats/numbers: IBM Plex Mono (scoreboard-style tabular figures)

All tokens are CSS custom properties in `tokens.css` — change them
there to re-theme the whole app.

## What's connected vs. what needs your Groq key

Everything routes correctly and was tested end-to-end against the real
Django backend in development: registration, the 3-step signup wizard,
login with JWT refresh, profile editing, workout template creation,
food search/logging against the local Filipino food database, and
navigation between all five modules.

**Two things need your own Groq API key to fully test**, since this
sandbox couldn't reach groq.com:
- `/coach` — the chat assistant (ChatDetail.jsx calls `sendMessage`)
- `/progress` — report generation (ReportsList.jsx calls `generateReport`)

Both already have working error handling — a missing/invalid key shows
a clear error banner rather than crashing — but the actual LLM response
quality/latency is unverified on my end. Test these first once you have
your key.

Exercise search (`/workouts/new` → Add Exercise) also needs real
internet access to reach wger.de — same caveat as noted in the backend
README.

## Known simplifications worth knowing about

- No offline/service-worker support yet (the original thesis's PWA
  requirement) — this is a plain SPA. Adding a service worker via
  `vite-plugin-pwa` is a reasonable next step if you want true offline
  support for your evaluation.
- Optimistic chat UI rolls back cleanly on failure, but there's no
  retry/resend button yet — the user has to retype.
- No image uploads (before/after pictures mentioned in the original's
  Account Module) — not built here since the backend doesn't have that
  field yet either.
