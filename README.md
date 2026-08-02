# Gig Radar (scheduled, no server to run)

Checks Ticketmaster, SeatGeek, and Bandsintown on a timer — via GitHub Actions,
for free — and writes results to a JSON file. A plain HTML page displays
whatever the last scheduled run found. Nothing to keep open, nothing to run
yourself, no server bill.

## How the pieces fit together

- **`scripts/check.py`** — does the actual work: geocodes your ZIP, calls the
  three APIs, matches against your watchlist, emails/texts on new matches,
  writes `data/matches.json`.
- **`.github/workflows/check.yml`** — tells GitHub to run that script every 3
  hours, automatically, forever, for free (on a public repo).
- **`watchlist.json`** — what you're tracking and where. Edit this file
  directly (via GitHub's web editor or locally) to change artists/genres,
  location, or contact info. No app, no form.
- **`index.html`** — the page you or your friend actually look at. It just
  reads `data/matches.json` and `watchlist.json` and displays them — it does
  no fetching or checking itself.
- **`scripts/scrapers.py`** — a template for band/org websites with no API.
  Empty by default; send me a real URL and I'll write the actual parsing
  logic for that specific page.

## Setup

**1. Create the repo.**
Go to github.com, create a new repository (public — required for free
scheduled Actions), and upload everything in this folder to it (drag-and-drop
on the repo's page works fine, or `git push` if you're comfortable with git).

**2. Add your API keys as secrets** (never committed to the repo itself).
In the repo: **Settings → Secrets and variables → Actions → New repository
secret**. Add whichever of these you have:
- `TICKETMASTER_API_KEY`
- `SEATGEEK_CLIENT_ID`
- `BANDSINTOWN_APP_ID`
- `SENDGRID_API_KEY` (for email alerts)
- `TWILIO_ACCOUNT_SID` / `TWILIO_AUTH_TOKEN` (for SMS alerts)

Any of these left out just means that source or channel is skipped — nothing
breaks.

**3. Edit `watchlist.json`** with your real ZIP code, radius, contact info,
and watchlist. Click the file on GitHub, click the pencil (edit) icon, change
the values, commit.

**4. Turn on GitHub Pages** so there's a real URL to visit:
**Settings → Pages → Source → Deploy from a branch → main → / (root) → Save.**
GitHub gives you a URL like `https://yourusername.github.io/gig-radar/` —
that's the page to bookmark or add to your home screen.

**5. Trigger the first run manually** instead of waiting 3 hours: go to the
**Actions** tab → **Check for gigs** → **Run workflow**. Watch it go green,
then reload your Pages URL — it should show whatever it found.

From here it just runs itself. Edit `watchlist.json` any time to change
what's tracked; the next scheduled run (or a manual one from the Actions tab)
picks it up.

## What this fixes vs. the earlier single-file version

- **Real push alerts again** — the script runs whether or not anyone has the
  page open, so email/SMS actually fire on a schedule, not just "when you
  think to check."
- **No API keys sitting in browser code** — they're GitHub secrets now,
  never visible in the page source.
- **Room for scraper-based sources** (band sites, local orgs) — those need a
  server to fetch from anyway (CORS blocks browsers from fetching arbitrary
  sites), so this is the first version that can actually add them.

## What's still true

Small bars with literally no ticketing platform or website structure still
have no clean source — that gap doesn't close on its own. `scrapers.py` is
where those get added, one site at a time, once there's a real page to look at.
