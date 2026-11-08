"""
Finds exercises mentioned in a coach reply and returns form videos for them.
The LLM never writes links (it would invent them) -- the backend attaches
them from the curated ExerciseVideo table. A staple exercise with no
curated video gets a YouTube search link instead.
"""

import re
from urllib.parse import quote_plus

from workouts.models import ExerciseVideo
from workouts.services.workout_generator import COMMON_EXERCISE_KEYWORDS

MAX_VIDEOS = 3


def _staple_keywords():
    seen = set()
    for keywords in COMMON_EXERCISE_KEYWORDS.values():
        for kw in keywords:
            seen.add(kw.lower())
    return seen


def find_exercise_videos(text):
    """
    Returns up to MAX_VIDEOS items, in the order they appear in `text`:
    {"name": str, "url": str, "kind": "video" | "search"}
    The most specific (longest) exercise name wins when names overlap, e.g.
    "goblet squat" beats "squat" for the same words.
    """
    if not text:
        return []

    candidates = []  # (key, label, url, kind)
    curated = set()
    for v in ExerciseVideo.objects.exclude(url=""):
        curated.add(v.name)
        candidates.append((v.name, v.name.title(), v.url, "video"))
    for kw in _staple_keywords():
        if kw not in curated:
            search = f"https://www.youtube.com/results?search_query={quote_plus(kw + ' proper form beginner')}"
            candidates.append((kw, kw.title(), search, "search"))

    # Longest first so specific names win; curated before search on ties.
    candidates.sort(key=lambda c: (-len(c[0]), c[3] != "video"))

    lowered = text.lower()
    taken = []
    found = []
    for key, label, url, kind in candidates:
        m = re.search(rf"\b{re.escape(key)}(?:e?s)?\b", lowered)
        if not m:
            continue
        start, end = m.span()
        if any(start < t_end and t_start < end for t_start, t_end in taken):
            continue
        taken.append((start, end))
        found.append((start, {"name": label, "url": url, "kind": kind}))

    found.sort(key=lambda f: f[0])
    return [item for _, item in found[:MAX_VIDEOS]]