"""
Diagnostic command for the wger integration. Run this directly to see
exactly what wger.de returns, bypassing the Django view/frontend
entirely -- useful when exercise search isn't working and you need to
see the raw response shape.

Usage: python manage.py test_wger [search term]
"""

import json

import requests
from django.core.management.base import BaseCommand

from workouts.wger_service import WGER_BASE_URL, WgerService


class Command(BaseCommand):
    help = "Test the wger.de API connection and print the raw response"

    def add_arguments(self, parser):
        parser.add_argument("term", nargs="?", default="bench press")

    def handle(self, *args, **options):
        term = options["term"]

        self.stdout.write(f"Testing connection to {WGER_BASE_URL} ...")
        try:
            resp = requests.get(f"{WGER_BASE_URL}/exercise/", params={"limit": 1, "format": "json"}, timeout=8)
            self.stdout.write(self.style.SUCCESS(f"Base connectivity OK (HTTP {resp.status_code})"))
        except requests.RequestException as exc:
            self.stdout.write(self.style.ERROR(f"Cannot reach wger.de at all: {exc}"))
            self.stdout.write("Check your internet connection / firewall / VPN before debugging further.")
            return

        self.stdout.write(f"\nSearching for '{term}' via the raw endpoint ...")
        try:
            raw = requests.get(
                f"{WGER_BASE_URL}/exercise/search/",
                params={"term": term, "language": "english", "format": "json"},
                timeout=8,
            )
            self.stdout.write(f"HTTP {raw.status_code}")
            self.stdout.write("Raw response:")
            self.stdout.write(json.dumps(raw.json(), indent=2)[:3000])
        except requests.RequestException as exc:
            self.stdout.write(self.style.ERROR(f"Search request failed: {exc}"))
            return
        except ValueError:
            self.stdout.write(self.style.ERROR(f"Response wasn't valid JSON. Raw text:"))
            self.stdout.write(raw.text[:1000])
            return

        self.stdout.write(f"\nParsed via WgerService.search_exercises('{term}') ...")
        try:
            results = WgerService.search_exercises(term)
            if results:
                self.stdout.write(self.style.SUCCESS(f"Got {len(results)} parsed result(s):"))
                for r in results:
                    self.stdout.write(f"  - {r['name']} (id={r['wger_exercise_id']})")
            else:
                self.stdout.write(
                    self.style.WARNING(
                        "Parsed 0 results. Compare the 'Raw response' above against the parsing "
                        "logic in workouts/wger_service.py -- the response shape may not match "
                        "what search_exercises() expects."
                    )
                )
        except Exception as exc:
            self.stdout.write(self.style.ERROR(f"WgerService raised: {exc}"))
