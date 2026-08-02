#!/usr/bin/env python3
"""
Gig Radar — server-side check, run on a schedule by GitHub Actions.

Reads watchlist.json for what to track and where. Reads API keys from
environment variables (set as GitHub Actions secrets, never committed).
Writes data/matches.json, which the static index.html page displays.
Sends email/SMS for genuinely new matches only.

Run locally to test: python scripts/check.py
"""

import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import requests

from scrapers import run_all_scrapers

BASE_DIR = Path(__file__).parent.parent
WATCHLIST_PATH = BASE_DIR / "watchlist.json"
MATCHES_PATH = BASE_DIR / "data" / "matches.json"


# ---------- config + state ----------

def load_watchlist_config() -> dict:
    with open(WATCHLIST_PATH) as f:
        return json.load(f)


def load_matches() -> dict:
    if MATCHES_PATH.exists():
        with open(MATCHES_PATH) as f:
            return json.load(f)
    return {"last_checked": None, "matches": []}


def save_matches(data: dict) -> None:
    MATCHES_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(MATCHES_PATH, "w") as f:
        json.dump(data, f, indent=2)


# ---------- geo ----------

def geocode_zip(zip_code: str) -> tuple[float, float]:
    r = requests.get(f"https://api.zippopotam.us/us/{zip_code}", timeout=15)
    r.raise_for_status()
    place = r.json()["places"][0]
    return float(place["latitude"]), float(place["longitude"])


def miles_between(lat1, lng1, lat2, lng2) -> float:
    earth_radius_miles = 3958.8
    d_lat = math.radians(lat2 - lat1)
    d_lng = math.radians(lng2 - lng1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lng / 2) ** 2
    )
    return earth_radius_miles * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# ---------- fetching ----------

def fetch_ticketmaster(api_key: str, lat: float, lng: float, radius: float) -> list[dict]:
    shows = []
    page = 0
    while True:
        params = {
            "apikey": api_key, "latlong": f"{lat},{lng}", "radius": str(int(radius)),
            "unit": "miles", "classificationName": "music", "page": str(page), "size": "100",
        }
        r = requests.get("https://app.ticketmaster.com/discovery/v2/events.json", params=params, timeout=15)
        if r.status_code != 200:
            print(f"  Ticketmaster request failed: {r.status_code}")
            break
        data = r.json()
        events = data.get("_embedded", {}).get("events", [])
        for e in events:
            venues = e.get("_embedded", {}).get("venues", [])
            if not venues or not venues[0].get("location", {}).get("latitude"):
                continue
            v = venues[0]
            attractions = e.get("_embedded", {}).get("attractions", [])
            artist = attractions[0]["name"] if attractions else e.get("name")
            genres = set()
            for c in e.get("classifications", []):
                if c.get("genre", {}).get("name"):
                    genres.add(c["genre"]["name"])
                if c.get("subGenre", {}).get("name"):
                    genres.add(c["subGenre"]["name"])
            shows.append({
                "id": f"tm_{e['id']}", "artist": artist, "venue": v.get("name", "Unknown venue"),
                "genres": list(genres), "date": e.get("dates", {}).get("start", {}).get("localDate", "TBD"),
                "url": e.get("url"),
            })
        total_pages = data.get("page", {}).get("totalPages", 1)
        page += 1
        if page >= total_pages or not events:
            break
    return shows


def fetch_seatgeek(client_id: str, lat: float, lng: float, radius: float) -> list[dict]:
    shows = []
    page = 1
    while True:
        params = {
            "client_id": client_id, "lat": str(lat), "lon": str(lng),
            "range": f"{int(radius)}mi", "per_page": "100", "page": str(page),
        }
        r = requests.get("https://api.seatgeek.com/2/events", params=params, timeout=15)
        if r.status_code != 200:
            print(f"  SeatGeek request failed: {r.status_code}")
            break
        data = r.json()
        events = data.get("events", [])
        for e in events:
            venue = e.get("venue", {})
            performers = e.get("performers", [])
            artist = performers[0]["name"] if performers else e.get("title", "Unknown")
            genres = set()
            for p in performers:
                for g in p.get("genres", []):
                    if g.get("name"):
                        genres.add(g["name"])
            shows.append({
                "id": f"sg_{e['id']}", "artist": artist, "venue": venue.get("name", "Unknown venue"),
                "genres": list(genres), "date": (e.get("datetime_local") or "TBD")[:10],
                "url": e.get("url"),
            })
        total_pages = math.ceil((data.get("meta", {}).get("total", 0)) / 100)
        page += 1
        if page > total_pages or not events:
            break
    return shows


def fetch_bandsintown(app_id: str, artist_name: str, lat: float, lng: float, radius: float) -> list[dict]:
    encoded = quote(artist_name, safe="")
    r = requests.get(
        f"https://rest.bandsintown.com/artists/{encoded}/events",
        params={"app_id": app_id, "date": "upcoming"}, timeout=15,
    )
    if r.status_code == 404:
        return []
    if r.status_code != 200:
        print(f"  Bandsintown request failed for {artist_name}: {r.status_code}")
        return []

    shows = []
    for e in r.json():
        v = e.get("venue", {})
        if not v.get("latitude"):
            continue
        if miles_between(lat, lng, float(v["latitude"]), float(v["longitude"])) > radius:
            continue
        shows.append({
            "id": f"bt_{e['id']}", "artist": artist_name, "venue": v.get("name", "Unknown venue"),
            "genres": [], "date": (e.get("datetime") or "TBD")[:10], "url": e.get("url"),
        })
    return shows


# ---------- matching ----------

def matches_watchlist(show: dict, watchlist: list[dict]) -> bool:
    artist_lower = show["artist"].lower()
    tags_lower = [g.lower() for g in show["genres"]]
    for item in watchlist:
        value = item["value"].lower()
        if item["kind"] == "artist" and (value in artist_lower or artist_lower in value):
            return True
        if item["kind"] == "genre" and any(value in tag for tag in tags_lower):
            return True
    return False


# ---------- notifying ----------

def send_email(config: dict, show: dict) -> None:
    if not config.get("friend_email") or not os.environ.get("SENDGRID_API_KEY"):
        return
    from sendgrid import SendGridAPIClient
    from sendgrid.helpers.mail import Mail

    body = f"{show['artist']} at {show['venue']} — {show['date']}."
    if show.get("url"):
        body += f"\n{show['url']}"

    msg = Mail(
        from_email=config["sendgrid_from_email"], to_emails=config["friend_email"],
        subject=f"\U0001f3b5 {show['artist']} is playing near you",
        plain_text_content=body,
    )
    try:
        SendGridAPIClient(os.environ["SENDGRID_API_KEY"]).send(msg)
    except Exception as ex:
        print(f"  Email send failed: {ex}")


def send_sms(config: dict, show: dict) -> None:
    if not config.get("friend_phone") or not os.environ.get("TWILIO_ACCOUNT_SID"):
        return
    from twilio.rest import Client

    body = f"{show['artist']} at {show['venue']} — {show['date']}. {show.get('url', '')}"
    try:
        Client(os.environ["TWILIO_ACCOUNT_SID"], os.environ["TWILIO_AUTH_TOKEN"]).messages.create(
            to=config["friend_phone"], from_=config["twilio_from_number"], body=body
        )
    except Exception as ex:
        print(f"  SMS send failed: {ex}")


# ---------- main ----------

def main() -> None:
    config = load_watchlist_config()
    stored = load_matches()
    existing_ids = {m["id"] for m in stored["matches"]}

    try:
        lat, lng = geocode_zip(config["home_zip"])
    except Exception as ex:
        print(f"Could not geocode ZIP {config['home_zip']}: {ex}")
        return
    radius = config["radius_miles"]
    print(f"Checking within {radius} mi of ZIP {config['home_zip']} ({lat}, {lng})")

    all_shows = []

    tm_key = os.environ.get("TICKETMASTER_API_KEY")
    if tm_key:
        print("Fetching Ticketmaster...")
        all_shows += fetch_ticketmaster(tm_key, lat, lng, radius)

    sg_client_id = os.environ.get("SEATGEEK_CLIENT_ID")
    if sg_client_id:
        print("Fetching SeatGeek...")
        all_shows += fetch_seatgeek(sg_client_id, lat, lng, radius)

    bt_app_id = os.environ.get("BANDSINTOWN_APP_ID")
    if bt_app_id:
        artist_watches = [w["value"] for w in config["watchlist"] if w["kind"] == "artist"]
        for artist in artist_watches:
            print(f"Fetching Bandsintown for {artist}...")
            all_shows += fetch_bandsintown(bt_app_id, artist, lat, lng, radius)

    print("Running any configured site scrapers...")
    all_shows += run_all_scrapers()

    print(f"Fetched {len(all_shows)} candidate show(s)")

    new_matches = []
    for show in all_shows:
        if show["id"] in existing_ids:
            continue
        if not matches_watchlist(show, config["watchlist"]):
            continue
        print(f"  MATCH: {show['artist']} at {show['venue']} on {show['date']}")
        send_email(config, show)
        send_sms(config, show)
        new_matches.append(show)
        existing_ids.add(show["id"])

    stored["matches"] = stored["matches"] + new_matches
    stored["last_checked"] = datetime.now(timezone.utc).isoformat()
    save_matches(stored)

    print(f"Done — {len(new_matches)} new match(es), {len(stored['matches'])} total on file")


if __name__ == "__main__":
    main()
