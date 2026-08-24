#!/usr/bin/env bash
#
# json_stats.sh — Show JSON generation statistics for the last N days
#
# Usage:
#   ./json_stats.sh [days] [folder]
#
#   days    Number of days to look back (default: 3)
#   folder  Folder to scan for *_analyzed.json files (default: ~/enhanced)
#
# Examples:
#   ./json_stats.sh              # last 3 days, ~/enhanced
#   ./json_stats.sh 7            # last 7 days, ~/enhanced
#   ./json_stats.sh 1 /tmp/out   # today only, custom folder
#
set -euo pipefail

DAYS="${1:-3}"
FOLDER="${2:-$HOME/enhanced}"

# Resolve symlinks (~/enhanced is a symlink to /media/.../enhanced)
REAL="$(readlink -f "$FOLDER")"

if [[ ! -d "$REAL" ]]; then
    echo "Error: folder '$FOLDER' does not exist" >&2
    exit 1
fi

# Calculate date range: from N days ago at 00:00 until tomorrow at 00:00
START_DATE=$(date -d "-$((DAYS - 1)) days" +%Y-%m-%d)
END_DATE=$(date -d "+1 day" +%Y-%m-%d)

echo "Scanning: $REAL"
echo "Range:   $START_DATE → $(date -d "-1 day $END_DATE" +%Y-%m-%d) ($DAYS day(s))"
echo ""

# Collect timestamps (sorted)
TMPFILE=$(mktemp)
trap 'rm -f "$TMPFILE"' EXIT

find -L "$REAL" -name "*.json" \
    -newermt "$START_DATE 00:00:00" \
    ! -newermt "$END_DATE 00:00:00" \
    -printf '%T+ %p\n' 2>/dev/null \
    | sort > "$TMPFILE"

TOTAL=$(wc -l < "$TMPFILE")

if [[ "$TOTAL" -eq 0 ]]; then
    echo "No JSON files found in that range."
    exit 0
fi

# Per-day stats
awk -F'+' '
    { split($2, t, ":"); sec = t[1]*3600 + t[2]*60 + t[3]; print $1, sec }
' "$TMPFILE" | awk '
    {
        date = $1; sec = $2
        if (date != prev_date && prev_date != "") {
            span = last_sec - first_sec
            printf "  %-12s %4d files  %02d:%02d-%02d:%02d  span=%dh%02dm  %.1f s/file  (%.1f min/file)\n",
                prev_date, count,
                int(first_sec/3600), int((first_sec%3600)/60),
                int(last_sec/3600),  int((last_sec%3600)/60),
                int(span/3600), int((span%3600)/60),
                span/count, span/count/60
        }
        if (date != prev_date) { count = 0; first_sec = sec }
        count++
        last_sec = sec
        prev_date = date
    }
    END {
        span = last_sec - first_sec
        printf "  %-12s %4d files  %02d:%02d-%02d:%02d  span=%dh%02dm  %.1f s/file  (%.1f min/file)\n",
            prev_date, count,
            int(first_sec/3600), int((first_sec%3600)/60),
            int(last_sec/3600),  int((last_sec%3600)/60),
            int(span/3600), int((span%3600)/60),
            span/count, span/count/60
    }
'

echo ""
echo "  Total: $TOTAL files over $DAYS day(s)"
