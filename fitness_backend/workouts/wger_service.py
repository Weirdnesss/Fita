"""
Thin client around the public wger.de REST API (v2). No API key is
required for read-only exercise data. Docs: https://wger.readthedocs.io/en/latest/api/api.html

NOTE on architecture: this module is NOT used for live exercise
search anymore -- ExerciseSearchView (views.py) searches the local
WgerExercise cache instead, populated by
`python manage.py sync_wger_exercises`. wger's undocumented
/exercise/search/ endpoint (used here in search_exercises(), kept for
the `test_wger` diagnostic command) returned a 404 in production
testing -- it's internal-only tooling per wger GitHub issue #329 and
isn't guaranteed to exist or keep its shape. Prefer the local cache
for anything user-facing.
"""

import requests

WGER_BASE_URL = "https://wger.de/api/v2"
DEFAULT_LANGUAGE = 2  # English, per wger's language table
REQUEST_TIMEOUT = 8


class WgerAPIError(Exception):
    pass


class WgerService:
    @staticmethod
    def _get(path, params=None):
        try:
            resp = requests.get(
                f"{WGER_BASE_URL}/{path}/",
                params={"format": "json", **(params or {})},
                timeout=REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            raise WgerAPIError(f"wger API request failed: {exc}") from exc

    @classmethod
    def search_exercises(cls, term, limit=10):
        """
        Search exercises by name. Uses wger's search endpoint (used by
        their own autocomplete UI). Note: the `language` param takes the
        full language name ("english"), not an ISO code ("en") -- using
        "en" here previously caused every search to return no results.
        """
        data = cls._get(
            "exercise/search",
            {"term": term, "language": "english", "limit": limit},
        )

        # Defensive parsing: the endpoint is undocumented (wger GitHub
        # issue #329) and its exact shape isn't guaranteed to stay
        # stable. Handle the known "suggestions" shape, a plain DRF
        # paginated "results" shape, and a bare list, so a shape change
        # degrades to zero results instead of raising.
        if isinstance(data, list):
            suggestions = data
        elif isinstance(data, dict):
            suggestions = data.get("suggestions") or data.get("results") or []
        else:
            suggestions = []

        results = []
        for item in suggestions:
            if not isinstance(item, dict):
                continue
            payload = item.get("data", item)
            name = payload.get("name") or payload.get("value", "")
            exercise_id = payload.get("base_id") or payload.get("id")
            if not name or not exercise_id:
                continue
            results.append(
                {
                    "wger_exercise_id": exercise_id,
                    "name": name,
                    "category": payload.get("category", ""),
                    "image": payload.get("image"),
                }
            )
        return results[:limit]

    @classmethod
    def get_exercise_detail(cls, wger_exercise_id):
        """
        Full detail for a single exercise (description, muscles,
        equipment) -- used when adding an exercise to a template so we
        can store category/equipment names locally.
        """
        data = cls._get(f"exerciseinfo/{wger_exercise_id}")
        translations = data.get("translations", [])
        english = next(
            (t for t in translations if t.get("language") == DEFAULT_LANGUAGE),
            translations[0] if translations else {},
        )
        category = data.get("category", {}) or {}
        equipment_list = data.get("equipment", []) or []
        return {
            "wger_exercise_id": wger_exercise_id,
            "name": english.get("name", "Unknown Exercise"),
            "description": english.get("description", ""),
            "category_name": category.get("name", ""),
            "equipment_name": ", ".join(e.get("name", "") for e in equipment_list),
        }
