"""
Scrapers for sites with no API — band websites, local music orgs, etc.

There's no generic way to do this: every site lays out its show dates
differently, so each one needs its own small function that knows where
to look on that specific page. This file is deliberately empty of real
scrapers to start — it's a template to fill in once you have an actual
URL to look at.

Two things worth checking before writing one, per site:
  1. Its robots.txt (e.g. https://example.org/robots.txt) — tells you
     what the site owner is and isn't OK with a bot reading.
  2. Whether the page's HTML actually contains the show info directly,
     or loads it in with JavaScript after the page loads — the second
     kind can't be scraped with `requests` alone and needs a real
     browser (Playwright/Selenium), which is a much bigger dependency.

HOW TO ADD ONE:
  1. View the page's source (not just what you see rendered — the raw
     HTML) and find the repeating pattern each show/event uses.
  2. Write a function here that takes the page's HTML and returns a
     list of dicts shaped like the other sources:
       {
         "id": "some_stable_unique_string",   # so we never re-alert on it
         "artist": "...",
         "venue": "...",
         "genres": [],                        # usually empty, that's fine
         "date": "YYYY-MM-DD" or "TBD",
         "url": "...",
       }
  3. Add it to SCRAPERS below with a name.

Send me the actual URL(s) and I'll write the real parsing logic for
that specific page — it's not something that can be guessed in advance.
"""

import requests

REQUEST_HEADERS = {
    "User-Agent": "GigRadar/1.0 (personal, non-commercial gig tracker)"
}


def example_scraper(base_url: str) -> list[dict]:
    """
    Template only — replace the parsing below once there's a real page
    to look at. This function intentionally returns nothing so it never
    silently reports fake matches.
    """
    try:
        requests.get(base_url, headers=REQUEST_HEADERS, timeout=15)
    except Exception:
        pass
    return []


# Register real scrapers here once they're written, e.g.:
# SCRAPERS = {
#     "some_blues_org": lambda: parse_blues_org("https://example.org/shows"),
# }
SCRAPERS: dict = {}


def run_all_scrapers() -> list[dict]:
    results = []
    for name, fn in SCRAPERS.items():
        try:
            results.extend(fn())
        except Exception as ex:
            print(f"  Scraper '{name}' failed: {ex}")
    return results
