#!/usr/bin/env bash
# Build an installable Kodi zip of the addon.
#
# The add-on source lives at the repo root, but Kodi requires the archive to
# contain a single top-level folder named after the add-on id, with addon.xml
# inside it. We therefore stage the add-on files under that folder name before
# zipping.
#
# This script is deliberately addon-agnostic: the add-on id and version are read
# from addon.xml, and the archive contents are "everything in the repo root
# except the development/build artefacts listed in EXCLUDE". Copy it verbatim
# into any Kodi add-on repo and it works with no edits.
#
# Builds to a temp file, verifies the archive is intact, and only then moves it
# into place atomically. This guarantees Kodi never sees a half-written or stale
# archive — a partially written / inconsistent zip makes Kodi's reader compute
# wrong offsets and fail with "Unable to load addon.xml / Error reading Element
# value".
set -euo pipefail
cd "$(dirname "$0")"

# Read the add-on id and version from its manifest. Collapsing newlines lets the
# regex span the multi-line <addon ...> opening tag; [^>]* keeps the match
# inside that tag so we never pick up an <import>'s attributes.
MANIFEST=$(tr '\n' ' ' < addon.xml)
ADDON=$(sed -n 's/.*<addon[^>]*[[:space:]]id="\([^"]*\)".*/\1/p' <<<"$MANIFEST")
VERSION=$(sed -n 's/.*<addon[^>]*[[:space:]]version="\([^"]*\)".*/\1/p' <<<"$MANIFEST")
if [ -z "$ADDON" ]; then
    echo "ERROR: could not read add-on id from addon.xml." >&2
    exit 1
fi
if [ -z "$VERSION" ]; then
    echo "ERROR: could not read version from addon.xml." >&2
    exit 1
fi

# Repo-root entries that are development/build artefacts and must not ship inside
# the add-on. Patterns are matched against each top-level entry name (globs are
# fine). Anything not listed here becomes part of the add-on, so a new add-on
# with different content files needs no changes.
EXCLUDE=(.git .github .gitignore package.sh '*.zip' '*.zip.tmp' '*.xcf')

# Build the contents list: every top-level entry except the excluded ones.
shopt -s nullglob dotglob
CONTENTS=()
for entry in *; do
    skip=0
    for pat in "${EXCLUDE[@]}"; do
        # shellcheck disable=SC2254
        case "$entry" in $pat) skip=1; break ;; esac
    done
    [ "$skip" -eq 0 ] && CONTENTS+=("$entry")
done
shopt -u dotglob
if [ ${#CONTENTS[@]} -eq 0 ]; then
    echo "ERROR: nothing to package (all root entries excluded)." >&2
    exit 1
fi

OUT="${ADDON}-${VERSION}.zip"
TMP="${OUT}.tmp"

rm -f "$TMP"

# Stage the add-on under a folder named after the add-on id so the archive has
# the layout Kodi expects. The staging dir is cleaned up on any exit.
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
mkdir -p "$STAGE/$ADDON"
cp -R "${CONTENTS[@]}" "$STAGE/$ADDON/"

# -X strips extra file attributes (extended timestamps, uid/gid) for a lean,
# maximally portable archive. __pycache__/.pyc are excluded from the build.
( cd "$STAGE" && zip -r -X "$ADDON.zip" "$ADDON" -x '*/__pycache__/*' '*.pyc' >/dev/null )
mv "$STAGE/$ADDON.zip" "$TMP"

# Verify every entry's CRC before publishing.
if ! unzip -tqq "$TMP" >/dev/null; then
    echo "ERROR: built archive failed integrity check; not publishing." >&2
    rm -f "$TMP"
    exit 1
fi

# Sanity-check the manifest is present and readable in the archive.
if ! unzip -p "$TMP" "${ADDON}/addon.xml" | grep -q '<addon'; then
    echo "ERROR: ${ADDON}/addon.xml missing or unreadable in archive." >&2
    rm -f "$TMP"
    exit 1
fi

mv -f "$TMP" "$OUT"
echo "Created $OUT ($(unzip -l "$OUT" | tail -1 | awk '{print $2}') files)"
