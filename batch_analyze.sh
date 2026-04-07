#!/usr/bin/env bash
# Analyze images one at a time, stopping Ollama between each to free memory.
# Usage: ./batch_analyze.sh [IMAGE_DIR] [OUTPUT_DIR]

set -uo pipefail

IMAGE_DIR="${1:-Goes}"
OUTPUT_DIR="${2}"
MODEL="llama3.2-vision:11b"
PYTHON=".venv/bin/python"

mkdir -p "$OUTPUT_DIR"

# Collect images
mapfile -t images < <(ls "$IMAGE_DIR"/*.jpg "$IMAGE_DIR"/*.JPG "$IMAGE_DIR"/*.jpeg 2>/dev/null | sort)
total=${#images[@]}

if [ "$total" -eq 0 ]; then
    echo "No images found in $IMAGE_DIR"
    exit 1
fi

echo "Found $total images in $IMAGE_DIR → output: $OUTPUT_DIR"
echo "Model: $MODEL"
echo ""

idx=0
skip_count=0
ok_count=0
fail_count=0
batch_start=$(date +%s)

is_complete() {
    local json="$1"
    [ -f "$json" ] || return 1
    local scene
    scene=$("$PYTHON" -c "
import json, sys
try:
    d = json.load(open('$json'))
    m = d.get('metadata') or {}
    print('ok' if any(v for v in m.values() if v) else '')
except:
    print('')
" 2>/dev/null)
    [ "$scene" = "ok" ]
}

for img in "${images[@]}"; do
    ((idx++)) || true
    stem=$(basename "$img")
    stem_noext="${stem%.*}"
    json="$OUTPUT_DIR/${stem_noext}_analyzed.json"

    if is_complete "$json"; then
        ((skip_count++)) || true
        echo "[$idx/$total] SKIP (already done): $stem"
        continue
    fi

    echo ""
    echo "════════════════════════════════════════════════════════"
    echo "[$idx/$total] Analyzing: $img"
    echo "  Started: $(date '+%Y-%m-%d %H:%M:%S')"
    echo "────────────────────────────────────────────────────────"

    img_start=$(date +%s)

    "$PYTHON" -m picture_analyzer analyze "$img" \
        --pipeline-mode stepped \
        --restore-slide auto \
        --enhance \
        -o "$OUTPUT_DIR/" 2>&1
    exit_code=${PIPESTATUS[0]}

    img_end=$(date +%s)
    img_elapsed=$((img_end - img_start))
    mins=$((img_elapsed / 60))
    secs=$((img_elapsed % 60))

    echo "────────────────────────────────────────────────────────"
    if [ $exit_code -eq 0 ] && is_complete "$json"; then
        echo "  ✓ Complete in ${mins}m${secs}s"
        ((ok_count++)) || true
    else
        echo "  ✗ Failed or empty result after ${mins}m${secs}s (exit code: $exit_code)"
        ((fail_count++)) || true
    fi

    echo "  Stopping Ollama model to free memory..."
    ollama stop "$MODEL" 2>/dev/null || true
    sleep 2
done

batch_end=$(date +%s)
batch_elapsed=$((batch_end - batch_start))
batch_mins=$((batch_elapsed / 60))
batch_secs=$((batch_elapsed % 60))

echo ""
echo "════════════════════════════════════════════════════════"
echo "Batch complete"
echo "  Total time : ${batch_mins}m${batch_secs}s"
echo "  Processed  : $ok_count succeeded, $fail_count failed"
echo "  Skipped    : $skip_count (already done)"
echo "  Output dir : $OUTPUT_DIR"
