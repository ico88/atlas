#!/usr/bin/env bash
# Generate a CycloneDX-style SBOM (software bill of materials) for the ATLAS
# Python dependencies (ROADMAP R5 — supply-chain security). Reads the pinned
# `name==version` requirements so it is deterministic and needs no network.
#
# Usage: infrastructure/scripts/sbom.sh [output.json]
# The frontend SBOM is produced separately with `npm sbom` (see CI).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUT="${1:-sbom.python.json}"

# Collect "name==version" lines from every requirements file (skip comments,
# includes and editable installs), de-duplicated.
collect_components() {
  local first=1 name ver line
  while IFS= read -r line; do
    line="${line%%#*}"                      # strip comments
    line="${line//[[:space:]]/}"            # strip whitespace
    [ -z "$line" ] && continue
    case "$line" in -r*|-e*|.*) continue ;; esac
    [[ "$line" == *"=="* ]] || continue
    name="${line%%==*}"
    ver="${line##*==}"
    ver="${ver%%[<>;~!]*}"                   # drop any trailing markers
    [ "$first" -eq 1 ] || printf ',\n'
    first=0
    printf '    {"type":"library","name":"%s","version":"%s","purl":"pkg:pypi/%s@%s"}' \
      "$name" "$ver" "$name" "$ver"
  done
}

reqs() {
  cat \
    "$ROOT/apps/backend/requirements.txt" \
    "$ROOT/services/node-agent/requirements.txt" 2>/dev/null \
    | sort -u
}

{
  printf '{\n'
  printf '  "bomFormat": "CycloneDX",\n  "specVersion": "1.5",\n'
  printf '  "components": [\n'
  reqs | collect_components
  printf '\n  ]\n}\n'
} > "$OUT"

echo "Wrote $OUT ($(grep -c '"purl"' "$OUT") components)."
