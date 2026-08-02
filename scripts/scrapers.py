"""
Scrapers for sites with no API — band websites, local music orgs, etc.

There's no generic way to do this: every site lays out its show dates
differently, so each one needs its own small function that knows where
to look on that specific page.

Two things worth checking before writing a new one, per site:
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

CURRENT SCRAPERS:
  - scbtma_upcoming_shows: South Carolina Bluegrass & Traditional Music
    Association homepage. NOTE: this site is built on Wix. The homepage
    showed real show listings when checked, but the same site's separate
    /calendar page came back empty of events when fetched without
    JavaScript — a sign Wix may render some content client-side. If this
    scraper consistently returns zero shows once it's actually running,
    that's the likely explanation, and the fix would require a headless
    browser (out of scope for this project's "keep it simple" approach).
  - atlanta_blues_society_calendar: Atlanta Blues Society's calendar
    page. This one's WordPress (plain server-rendered HTML, no JS
    dependency), but the listings are free-text prose rather than tidy
    structured markup, so the parser works off text patterns. It's
    tested against the four real phrasing variants this site actually
    uses ("Artist, venue, city", "Artist host Event at Venue",
    "Artist w/ Other at Venue", "Artist at Venue, City") but is
    inherently more fragile than an API — if the site's writers change
    their phrasing conventions, this may need small tweaks.
"""

import math
import re
from datetime import datetime

import requests
from bs4 import BeautifulSoup

REQUEST_HEADERS = {
    "User-Agent": "GigRadar/1.0 (personal, non-commercial gig tracker)"
}

MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"


def _parse_month_day_year(month: str, day: str, year: str) -> str | None:
    try:
        return datetime.strptime(f"{month} {day} {year}", "%B %d %Y").strftime("%Y-%m-%d")
    except ValueError:
        return None


def _miles_between(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    earth_radius_miles = 3958.8
    d_lat = math.radians(lat2 - lat1)
    d_lng = math.radians(lng2 - lng1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lng / 2) ** 2
    )
    return earth_radius_miles * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# ---------- South Carolina Bluegrass & Traditional Music Association ----------
# Single fixed venue for every show it lists, so its coordinates are hardcoded
# here rather than geocoded on every run.
_SCBTMA_VENUE = "Bill's Music Shop & Pickin' Parlor, West Columbia SC"
_SCBTMA_LAT, _SCBTMA_LNG = 33.9987, -81.0748

_SCBTMA_DATE_RE = re.compile(
    rf"^(?:[A-Za-z]+day,\s*)?({MONTHS})\s+(\d{{1,2}}),\s*(\d{{4}})\s*$"
)


def scbtma_upcoming_shows(home_lat: float, home_lng: float, radius: float,
                          base_url: str = "https://www.scbtma.com/") -> list[dict]:
    if _miles_between(home_lat, home_lng, _SCBTMA_LAT, _SCBTMA_LNG) > radius:
        return []

    try:
        r = requests.get(base_url, headers=REQUEST_HEADERS, timeout=15)
        r.raise_for_status()
    except Exception as ex:
        print(f"  scbtma_upcoming_shows request failed: {ex}")
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    text = soup.get_text("\n")
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]

    shows = []
    prev_line = None
    for line in lines:
        m = _SCBTMA_DATE_RE.match(line)
        if m and prev_line:
            month, day, year = m.groups()
            date = _parse_month_day_year(month, day, year)
            if date:
                artist = prev_line
                shows.append({
                    "id": f"scbtma_{artist.lower().replace(' ', '_')}_{date}",
                    "artist": artist,
                    "venue": _SCBTMA_VENUE,
                    "genres": ["bluegrass"],
                    "date": date,
                    "url": base_url,
                })
        prev_line = line
    return shows


# ---------- Atlanta Blues Society ----------
# Venues vary per show and aren't individually geocoded (that would mean a
# geocode API call per unique venue name, which isn't worth the added
# complexity here). Instead this uses Atlanta's own coordinates as a
# stand-in for "the greater Atlanta blues scene" as a whole, since nearly
# all the venues this site lists cluster within that metro area anyway.
_ABS_LAT, _ABS_LNG = 33.7490, -84.3880

_ABS_DATE_LINE_RE = re.compile(
    rf"^\w+day,\s*({MONTHS})\s+(\d{{1,2}}),\s*(\d{{4}})(?:,\s*\d{{1,2}}(?::\d{{2}})?\s*[ap]m)?"
    rf"(?:,\s*\$?\d+)?:\s*(.+)$"
)
_ABS_ARTIST_SPLIT_RE = re.compile(r",| at | w/ | hosts | host ", re.IGNORECASE)
_URL_RE = re.compile(r"https?://\S+")


def atlanta_blues_society_calendar(home_lat: float, home_lng: float, radius: float,
                                    base_url: str = "https://atlantabluessociety.org/calendar/") -> list[dict]:
    if _miles_between(home_lat, home_lng, _ABS_LAT, _ABS_LNG) > radius:
        return []

    try:
        r = requests.get(base_url, headers=REQUEST_HEADERS, timeout=15)
        r.raise_for_status()
    except Exception as ex:
        print(f"  atlanta_blues_society_calendar request failed: {ex}")
        return []

    soup = BeautifulSoup(r.text, "html.parser")

    shows = []
    for idx, p in enumerate(soup.find_all("p")):
        line = re.sub(r"\s+", " ", p.get_text(" ", strip=True))
        m = _ABS_DATE_LINE_RE.match(line)
        if not m:
            continue
        month, day, year, rest = m.groups()
        date = _parse_month_day_year(month, day, year)
        if not date:
            continue

        url_match = _URL_RE.search(rest)
        url = url_match.group(0) if url_match else base_url
        rest_no_url = _URL_RE.sub("", rest).strip()

        artist = _ABS_ARTIST_SPLIT_RE.split(rest_no_url, maxsplit=1)[0].strip()
        if not artist:
            continue

        shows.append({
            "id": f"abs_{artist.lower().replace(' ', '_')}_{date}_{idx}",
            "artist": artist,
            "venue": rest_no_url,
            "genres": ["blues"],
            "date": date,
            "url": url,
        })
    return shows


SCRAPERS = {
    "scbtma": scbtma_upcoming_shows,
    "atlanta_blues_society": atlanta_blues_society_calendar,
}


def run_all_scrapers(home_lat: float, home_lng: float, radius: float) -> list[dict]:
    results = []
    for name, fn in SCRAPERS.items():
        try:
            results.extend(fn(home_lat, home_lng, radius))
        except Exception as ex:
            print(f"  Scraper '{name}' failed: {ex}")
    return results
