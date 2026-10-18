#!/bin/sh
# Cut a release: checks, bump VERSION, commit, tag, push.
#   ./release.sh [major|minor|patch] "what changed"
#   NO_PUSH=1 ./release.sh ...   # tag locally only
set -eu
cd "$(dirname "$0")"

part="${1:-patch}"
note="${2:-}"
case "$part" in major|minor|patch) ;; *) echo "usage: $0 [major|minor|patch] \"note\"" >&2; exit 2;; esac
[ -n "$note" ] || { echo "a release note is required" >&2; exit 2; }

[ "$(git rev-parse --abbrev-ref HEAD)" = "main" ] || { echo "release from main only" >&2; exit 1; }
[ -z "$(git status --porcelain)" ] || { echo "working tree not clean" >&2; exit 1; }

PY="${PYTHON:-$( [ -x .venv/bin/python ] && echo .venv/bin/python || echo python3 )}"
"$PY" scripts/check_denylist.py
"$PY" -m pytest -q
"$PY" build.py >/dev/null

old="$(cat VERSION)"
new="$(echo "$old" | awk -F. -v p="$part" '{
  if (p=="major") print $1+1".0.0"; else if (p=="minor") print $1"."$2+1".0"; else print $1"."$2"."$3+1 }')"
echo "$new" > VERSION

git add VERSION
git commit -q -m "Release v$new: $note"
git tag -a "v$new" -m "$note"
echo "released v$new (was v$old)"

if [ "${NO_PUSH:-0}" != "1" ]; then
  git push -q origin main --follow-tags
  echo "pushed v$new"
fi
