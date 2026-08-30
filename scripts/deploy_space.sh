#!/usr/bin/env bash
# Push Replay to a Hugging Face Space.
#
#   ./scripts/deploy_space.sh
#
# A Space needs its own README.md at the repository root, carrying the YAML
# frontmatter that tells Hugging Face which SDK and port to use. That clashes
# with the project README, so this builds a throwaway `space` branch where the
# Space card replaces the project README, pushes that branch to the Space, and
# leaves your working branch untouched.
#
# One-time setup:
#   1. Create the Space at https://huggingface.co/new-space (SDK: Docker)
#   2. git remote add space https://huggingface.co/spaces/<user>/<space>
#   3. Add AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY / AWS_REGION as Space
#      secrets, under Settings -> Variables and secrets

set -euo pipefail

BRANCH="${1:-main}"

if ! git remote get-url space >/dev/null 2>&1; then
  echo "No 'space' remote. Add it first:" >&2
  echo "  git remote add space https://huggingface.co/spaces/<user>/<space>" >&2
  exit 1
fi

if [ -n "$(git status --porcelain)" ]; then
  echo "Working tree is dirty. Commit or stash first." >&2
  exit 1
fi

START="$(git rev-parse --abbrev-ref HEAD)"
cleanup() { git checkout -q "$START"; }
trap cleanup EXIT

echo "Building the space branch from $START..."
git checkout -q -B space "$START"

cp deploy/huggingface/README.md README.md
git add README.md
git commit -q -m "Space card for Hugging Face"

echo "Pushing to the Space..."
git push -q --force space "space:$BRANCH"

echo
echo "Pushed. The Space will build the Dockerfile; watch the Logs tab."
echo "First build takes a few minutes."
