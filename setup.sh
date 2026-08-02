#!/usr/bin/env bash
set -euo pipefail

echo "== Gig Radar setup =="

if ! command -v gh >/dev/null 2>&1; then
  echo "GitHub CLI (gh) not found. Install it first:"
  echo "  brew install gh"
  exit 1
fi

if ! gh auth status >/dev/null 2>&1; then
  echo "Not logged into GitHub CLI yet -- starting login..."
  gh auth login
fi

if [ ! -f .env ]; then
  echo "No .env yet -- let's create one now."
  echo "Press Enter to skip any you don't have yet; you can add them later by"
  echo "editing .env and running this script again."
  echo
  read -rp "Ticketmaster API key: " tm_key
  read -rp "SeatGeek client ID: " sg_id
  read -rp "Bandsintown app ID: " bt_id
  read -rp "ntfy.sh topic (for the phone/iPad push alert): " ntfy_topic
  {
    echo "TICKETMASTER_API_KEY=$tm_key"
    echo "SEATGEEK_CLIENT_ID=$sg_id"
    echo "BANDSINTOWN_APP_ID=$bt_id"
    echo "NTFY_TOPIC=$ntfy_topic"
  } > .env
  echo
  echo ".env created."
fi

if [ -z "$(git config --global user.email 2>/dev/null || true)" ]; then
  echo "Git doesn't know your name/email yet. Run these two lines, then re-run this script:"
  echo '  git config --global user.name "Your Name"'
  echo '  git config --global user.email "you@example.com"'
  exit 1
fi

if ! grep -qxF ".env" .gitignore 2>/dev/null; then
  echo ".env" >> .gitignore
fi
if ! grep -qxF ".DS_Store" .gitignore 2>/dev/null; then
  echo ".DS_Store" >> .gitignore
fi

if [ ! -d .git ]; then
  echo "Initializing git repo..."
  git init -b main
fi

git add .
if ! git diff --cached --quiet; then
  git commit -m "Gig Radar setup"
else
  echo "Nothing new to commit."
fi

REPO_NAME=$(basename "$PWD")

if git remote get-url origin >/dev/null 2>&1; then
  echo "Remote 'origin' already set -- syncing with it before pushing (the Actions bot may have committed updates since your last run)..."
  if ! git pull --rebase origin main; then
    echo "Could not sync automatically -- there may be a real conflict to resolve."
    echo "Run 'git status' to see what's going on, then re-run this script."
    exit 1
  fi
  git push -u origin main
else
  echo "Creating GitHub repo '$REPO_NAME'..."
  gh repo create "$REPO_NAME" --public --source=. --remote=origin --push
fi

REPO_FULL=$(gh repo view --json nameWithOwner -q .nameWithOwner)
echo "Repo: https://github.com/$REPO_FULL"

echo "Uploading secrets from .env..."
while IFS='=' read -r key value; do
  case "$key" in ''|'#'*) continue ;; esac
  if [ -z "${value:-}" ]; then
    echo "  Skipping $key (empty in .env -- add it later with: gh secret set $key)"
    continue
  fi
  echo "  Setting $key"
  gh secret set "$key" --body "$value"
done < .env

echo "Enabling GitHub Pages..."
if gh api "repos/$REPO_FULL/pages" -X POST -f build_type=legacy -f "source[branch]=main" -f "source[path]=/" >/dev/null 2>&1; then
  echo "  Pages enabled."
else
  echo "  Could not enable Pages automatically (it may already be on) -- check Settings > Pages in the repo if the URL below doesn't load in a few minutes."
fi

echo "Triggering the first check run..."
if gh workflow run check.yml >/dev/null 2>&1; then
  echo "  Triggered -- check the Actions tab in a minute or two."
else
  echo "  Could not trigger it automatically -- run it manually from the repo's Actions tab."
fi

OWNER=$(echo "$REPO_FULL" | cut -d/ -f1)
NAME=$(echo "$REPO_FULL" | cut -d/ -f2)

echo
echo "Done."
echo "Repo:  https://github.com/$REPO_FULL"
echo "Pages: https://$OWNER.github.io/$NAME/"
echo "(Pages and the first Actions run can take a minute or two to finish.)"
