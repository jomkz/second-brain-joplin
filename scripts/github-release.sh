#!/usr/bin/env bash
# Create or update the GitHub Release for a version tag, with notes taken from
# that version's CHANGELOG.md section. Run by the release workflow after the PyPI
# publish; also safe to run by hand (for example to backfill an older tag).
#
#   scripts/github-release.sh v0.3.0 [dist/*]
#
# Idempotent: an existing release has its title, notes and pre-release flag
# rewritten and its assets replaced, so re-running a release never fails on
# "already exists". Needs `gh` authenticated with contents: write.
set -euo pipefail

tag="${1:?usage: $0 <vX.Y.Z> [asset ...]}"
shift
version="${tag#v}"
changelog="${CHANGELOG:-CHANGELOG.md}"

# The heading is "## [<version>] — <name>"; the section runs to the next "## ["
# heading or the link definitions at the end of the file.
heading="$(grep -m1 -F "## [$version]" "$changelog" || true)"
if [ -z "$heading" ]; then
  echo "error: $changelog has no '## [$version]' section" >&2
  exit 1
fi
name="${heading#"## [$version]"}"
name="${name# — }"
title="$tag${name:+ — $name}"

notes="$(mktemp)"
trap 'rm -f "$notes"' EXIT
awk -v h="## [$version]" '
  index($0, h) == 1 { found = 1; next }
  found && (/^## \[/ || /^\[[^]]+\]: /) { exit }
  found && !started && /^[[:space:]]*$/ { next }
  found { started = 1; print }
' "$changelog" > "$notes"
if ! grep -q '[^[:space:]]' "$notes"; then
  echo "error: the '## [$version]' section of $changelog is empty" >&2
  exit 1
fi

# PEP 440 pre-releases (0.4.0a1, 0.4.0b2, 0.4.0rc1, 0.4.0.dev1) and SemVer ones (0.4.0-rc.1).
prerelease=false
if [[ "$version" == *-* || "$version" =~ (a|b|rc|\.dev)[0-9]+$ ]]; then
  prerelease=true
fi

if gh release view "$tag" > /dev/null 2>&1; then
  gh release edit "$tag" --title "$title" --notes-file "$notes" --prerelease="$prerelease"
  if [ "$#" -gt 0 ]; then
    gh release upload "$tag" "$@" --clobber
  fi
  echo "updated release $tag (prerelease=$prerelease)"
else
  gh release create "$tag" "$@" --verify-tag --title "$title" --notes-file "$notes" \
    --prerelease="$prerelease"
  echo "created release $tag (prerelease=$prerelease)"
fi
