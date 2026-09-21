#!/usr/bin/env bash
# regen-status.sh — show which folders have been regenerated since a given date.
#
# Lists every album folder under the enhanced root (default: the configured
# output.enhanced_root) that contains *_enhanced.jpg files newer than the
# cutoff date, with per-folder progress and last-activity timestamps.
#
# Usage:
#   ./regen-status.sh                          # since Saturday 2026-09-19
#   ./regen-status.sh 2026-09-20               # since a specific date
#   ./regen-status.sh "2026-09-20 14:30"       # since a date+time
#   REGEN_ROOT=/some/root ./regen-status.sh    # non-default enhanced root
#
# Output columns:
#   done/total  last-activity   folder name
# Folders still in progress (done < total) are marked with "← in progress".
set -euo pipefail

CUTOFF="${1:-2026-09-19}"

# Resolve the enhanced root: REGEN_ROOT env var, else from config.yaml
if [[ -n "${REGEN_ROOT:-}" ]]; then
    ROOT="$REGEN_ROOT"
else
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    CONFIG="$SCRIPT_DIR/config.yaml"
    if [[ ! -f "$CONFIG" ]]; then
        echo "Error: config.yaml not found at $CONFIG" >&2
        echo "Set REGEN_ROOT=/path/to/enhanced to override." >&2
        exit 1
    fi
    ROOT="$("$SCRIPT_DIR/.venv/bin/python" -c "
import yaml
with open('$CONFIG') as f:
    cfg = yaml.safe_load(f)
print(cfg.get('output', {}).get('enhanced_root', ''))
")"
    if [[ -z "$ROOT" ]]; then
        echo "Error: output.enhanced_root not set in config.yaml" >&2
        echo "Set REGEN_ROOT=/path/to/enhanced to override." >&2
        exit 1
    fi
fi

if [[ ! -d "$ROOT" ]]; then
    echo "Error: enhanced root '$ROOT' does not exist" >&2
    exit 1
fi

printf "Enhanced root: %s\nCutoff:         %s\n\n" "$ROOT" "$CUTOFF"

total_done=0
total_images=0
folders=0

# Find folders with *_enhanced.jpg newer than cutoff (handles spaces in names)
find "$ROOT" -maxdepth 1 -type d -print0 2>/dev/null | sort -z |
while IFS= read -r -d '' d; do
    [[ "$d" == "$ROOT" ]] && continue

    n=$(find "$d" -maxdepth 1 -name "*_enhanced.jpg" -newermt "$CUTOFF" 2>/dev/null | wc -l)
    total=$(find "$d" -maxdepth 1 -name "*_enhanced.jpg" 2>/dev/null | wc -l)

    # Skip folders with no enhanced images at all
    [[ "$total" -eq 0 ]] && continue

    last=$(find "$d" -maxdepth 1 -name "*_enhanced.jpg" -newermt "$CUTOFF" \
           -printf "%TY-%Tm-%Td %TH:%TM\n" 2>/dev/null | sort -rn | head -1)

    marker=""
    if [[ "$n" -eq 0 ]]; then
        marker=""   # untouched by the regen run — not shown by default
        [[ "${SHOW_ALL:-0}" == "1" ]] && printf "%5s/%-5s %-17s %s %s\n" "$n" "$total" "${last:-—}" "$(basename "$d")" "← not started"
        continue
    elif [[ "$n" -lt "$total" ]]; then
        marker="← in progress"
    else
        marker="✓"
    fi

    printf "%5s/%-5s %-17s %s %s\n" "$n" "$total" "${last:-—}" "$(basename "$d")" "$marker"
done

echo
echo "Summary:"
find "$ROOT" -maxdepth 1 -type d -print0 2>/dev/null | while IFS= read -r -d '' d; do
    [[ "$d" == "$ROOT" ]] && continue
    find "$d" -maxdepth 1 -name "*_enhanced.jpg" -newermt "$CUTOFF" 2>/dev/null
done | wc -l | xargs printf "  images regenerated: %s\n"
find "$ROOT" -maxdepth 1 -type d -print0 2>/dev/null | while IFS= read -r -d '' d; do
    [[ "$d" == "$ROOT" ]] && continue
    n=$(find "$d" -maxdepth 1 -name "*_enhanced.jpg" -newermt "$CUTOFF" 2>/dev/null | wc -l)
    [[ "$n" -gt 0 ]] && echo x
done | wc -l | xargs printf "  folders touched:   %s\n"
echo "  (set SHOW_ALL=1 to also list untouched folders)"
