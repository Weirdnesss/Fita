"""
Bulk-fetches wger's exercise database into the local WgerExercise
cache. Run this once after setup, and periodically afterward (e.g.
monthly) to pick up new exercises.

Uses /api/v2/exerciseinfo/ -- a stable, documented, paginated
endpoint -- rather than the undocumented /exercise/search/ endpoint
that search_exercises() previously depended on directly. Searching
against a local cache is also faster and works even when wger.de is
briefly unreachable.

Note: /exerciseinfo/ returns heavily nested data (translations,
muscles, equipment per exercise), so it can be slow to respond,
especially at larger page sizes. This command uses a longer timeout
and smaller page size than the live-request helpers in
wger_service.py, plus a couple of retries on transient timeouts,
since a one-time bulk sync can afford to be patient.

Usage:
  python manage.py sync_wger_exercises            # full sync (~800+ exercises)
  python manage.py sync_wger_exercises --limit 50  # quick test run
"""

import time

import requests
from django.core.management.base import BaseCommand

from workouts.models import WgerExercise
from workouts.wger_service import WGER_BASE_URL, DEFAULT_LANGUAGE

SYNC_TIMEOUT = 30  # generous -- this is a one-time bulk job, not a live request
SYNC_PAGE_SIZE = 25  # smaller pages respond faster than the default 100
MAX_RETRIES = 3


class Command(BaseCommand):
    help = "Sync wger's exercise database into the local WgerExercise cache"

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Stop after syncing this many exercises (for quick testing)",
        )
        parser.add_argument(
            "--page-size",
            type=int,
            default=SYNC_PAGE_SIZE,
            help=f"Exercises per API request (default {SYNC_PAGE_SIZE}; lower if you keep timing out)",
        )
        parser.add_argument(
            "--timeout",
            type=int,
            default=SYNC_TIMEOUT,
            help=f"Seconds to wait per request (default {SYNC_TIMEOUT})",
        )

    def handle(self, *args, **options):
        limit = options["limit"]
        timeout = options["timeout"]
        url = f"{WGER_BASE_URL}/exerciseinfo/"
        params = {"language": DEFAULT_LANGUAGE, "limit": options["page_size"], "format": "json"}

        synced = 0
        page = 1
        self.stdout.write(f"Starting wger exercise sync (timeout={timeout}s, page_size={options['page_size']})...")

        while url:
            data = self._fetch_with_retry(url, params if page == 1 else None, timeout)
            if data is None:
                self.stdout.write(self.style.ERROR(f"Giving up on page {page} after {MAX_RETRIES} attempts."))
                self.stdout.write(
                    f"Progress so far ({synced} exercises) has been saved. Re-run the "
                    f"command to continue -- already-synced exercises will just be updated, not duplicated. "
                    f"Try --page-size 10 or --timeout 60 if timeouts persist."
                )
                break

            for item in data.get("results", []):
                translations = item.get("translations", [])
                english = next(
                    (t for t in translations if t.get("language") == DEFAULT_LANGUAGE),
                    None,
                )
                if not english or not english.get("name"):
                    continue  # skip exercises with no English translation

                category = item.get("category") or {}
                equipment_list = item.get("equipment") or []
                muscles = (item.get("muscles") or []) + (item.get("muscles_secondary") or [])
                muscle_names = ", ".join(
                    m.get("name", "") for m in muscles if isinstance(m, dict)
                )

                WgerExercise.objects.update_or_create(
                    id=item["id"],
                    defaults={
                        "name": english["name"],
                        "description": _strip_html(english.get("description", "")),
                        "category_name": category.get("name", ""),
                        "equipment_name": ", ".join(
                            e.get("name", "") for e in equipment_list if isinstance(e, dict)
                        ),
                        "muscle_names": muscle_names,
                    },
                )
                synced += 1

                if limit and synced >= limit:
                    self.stdout.write(self.style.SUCCESS(f"Reached --limit of {limit}. Stopping."))
                    return

            self.stdout.write(f"Page {page} done ({synced} synced so far)...")
            url = data.get("next")
            params = None  # 'next' already includes query params
            page += 1

        self.stdout.write(self.style.SUCCESS(f"Sync complete. {synced} exercises cached."))

    def _fetch_with_retry(self, url, params, timeout):
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = requests.get(url, params=params, timeout=timeout)
                resp.raise_for_status()
                return resp.json()
            except requests.Timeout:
                self.stdout.write(
                    self.style.WARNING(f"Timed out (attempt {attempt}/{MAX_RETRIES}), retrying...")
                )
                time.sleep(2 * attempt)  # brief backoff
            except requests.RequestException as exc:
                self.stdout.write(self.style.ERROR(f"Request failed: {exc}"))
                return None
            except ValueError:
                self.stdout.write(self.style.ERROR("Response wasn't valid JSON."))
                return None
        return None


def _strip_html(text):
    import re

    return re.sub(r"<[^>]+>", "", text or "").strip()
