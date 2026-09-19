# Enhancement Quality Audit

This document describes the audit methodology and results for the enhancement
pipeline (AI recommendations → `_enhanced.jpg` and restoration profiles →
`_restored_<profile>.jpg`), and how the findings were turned into pipeline
improvements.

All tooling lives in `enhancement_auditor.py` (standalone, read-only — it never
modifies photos). Results are written to `audit_output/` (gitignored).

## Why

The pipeline's enhancers had never been validated end-to-end. The central
question: **do the enhanced/restored versions actually beat the untouched
original, and are they the best we can do?**

## Methodology

1. **Stratified sample** — 50 images from `~/enhanced`, stratified by
   restoration profile × decade (guaranteed coverage of rare profiles like
   `red_cast`, spread across 1950s–2010s). Fixed seed, saved manifest,
   reproducible.

2. **Objective metrics** (local, free) — per variant: mean luminance, contrast
   (std-dev), saturation, color-cast ratio (R − avg(G,B)), highlight/shadow
   clipping %, sharpness (Laplacian variance). Deltas vs. the original catch
   over-processing with hard numbers.

3. **Blind LLM judging** (OpenAI gpt-4.1 — deliberately a different model than
   the analyzer, avoiding self-agreement bias):
   - All variants sent with randomized blind labels (A/B/C…) — the judge does
     not know which is the original. Scores each 1–10 per dimension
     (exposure, color fidelity, vibrancy, sharpness, artifacts, overall) and
     picks a winner.
   - Two judging styles: `--style faithful` (naturalness-first) and
     `--style vivid` (lively family-album look — matches the owner's
     preference, verified by comparing user picks against both styles).
   - A second call audits the analyzer's recommendations themselves:
     appropriate / too weak / too strong, profile choice correct, and what the
     parameters *should* have been (in the pipeline's own DSL).

4. **Iterative fix-and-verify cycles** — each pipeline change was followed by a
   regeneration + re-judge on the same sample, so every improvement (or
   regression) is measured. `regenerate --reuse-analysis` re-applies only the
   enhancement/restoration steps from existing analysis JSONs, isolating
   enhancement-side changes without re-running the LLM analyzer.

## Findings (v1 — original pipeline)

- **The untouched original won 62% of blind rankings.** The enhancers were
  making most photos worse.
- Restoration profiles were too aggressive (`faded`: saturation 1.5,
  contrast 1.6 — oversaturated, oversharpened, never won).
- Analyzer recommendations: too weak on dark slides (+5% brightness where
  +30–40% was needed), wrong cast direction (calling blue casts "warm" and
  warming them further), color ops on B&W photos.
- Hallucinated profile names created junk files (`_restored_foggy.jpg`).
- Judge style matters: under vivid judging the original's win rate dropped to
  38% — much of the "original wins" effect was naturalness bias. The owner's
  own preference (verified on specific images) matched the vivid style.

## Fixes applied (v2–v8 cycles)

| Cycle | Change | Effect (vivid judging) |
|-------|--------|------------------------|
| v2 | Prompt brightness recalibration + profile tuning | well_preserved wins 16%→42%; dark slides actually brightened |
| v3 | Cast-direction hard rules in prompts | Partial — small model only partially obeys prompt rules |
| v4 | **Cast-gate** (deterministic, in `SmartEnhancer`) | Cast drift halved 0.078→0.038; fidelity 4.34→4.82 |
| v5 | **Highlight-gate + saturation-gate** | Enhanced wins 14%→30%; blown highlights 29→21/50 |
| v6 | **Sharpness-gate** (caps, compounding prevention) | Enhanced wins 38% — top variant for the first time; max sharpening +363%→+150% |
| v7 | Flat exposure budget 0.35 | Overcorrected: vibrancy dropped, original won again (44%) |
| v8 | **Adaptive exposure budget** `0.35 + 0.40×(1−luma)` + bright-contrast cap | **Best state: enhanced 44% wins (top), original 36%, blown highlights 14/50** |

### The five gates (all active in `SmartEnhancer`)

The analyzer model (a small local Ollama model) only partially obeys prompt
rules, so the enhancer enforces limits by **measuring the original image
directly** (256px thumbnail, numpy):

| Gate | Trigger | Action |
|------|---------|--------|
| Cast | cast < 0.03 (neutral) | Drop color temperature + channel ops |
| Highlight | luma ≥ 0.45 or clipping ≥ 3% | Drop brightness increases + shadow brightening |
| Saturation | mean saturation ≥ 0.55 | Drop vibrance/saturation increases |
| Sharpness | lap_var ≥ 1900, or SHARPNESS + UNSHARP_MASK stacked | Drop/cap sharpening (≤ 1.15×, unsharp ≤ 60%) |
| Exposure budget | (b−1) + 0.5(c−1) + 0.5(shadows/100) > adaptive cap | Trim shadows → brightness → contrast |

Decreases always pass — gates only block changes that push past safe limits.
Measurement failure leaves gates open (fail-safe).

### Interaction with the `Enhancement: <tag>` mechanism

The description.txt tag (`black`/`blue`/`red`) steers the **analyzer's
diagnosis** (folder-level prior knowledge); the gates verify against the
**actual image** (per-image reality check). Both layers work together: the tag
prevents under-correction on folders with known systematic issues, the gates
prevent over-correction on individual images that don't match the folder
pattern. Keep using tags.

## Final results

| Metric | v1 (before) | v8 (after) |
|--------|-------------|------------|
| Enhanced wins blind ranking | 14% | **44%** (top variant) |
| Original wins | 62% | 36% |
| Blown highlights | 29/50 | 14/50 |
| Cast drift | 0.084 | 0.038 |
| Max sharpening increase | +363% | +150% |
| Recommendation "appropriate" | 8/50 | ~17/50 |
| Profile choice correct | 16/50 | ~33/50 |

## Re-running the audit

```bash
# Full cycle on a fresh sample
python3 enhancement_auditor.py sample --seed <new-seed>
python3 enhancement_auditor.py metrics
python3 enhancement_auditor.py judge --style vivid
python3 enhancement_auditor.py report --style vivid
python3 enhancement_auditor.py scores --style vivid

# Re-verify enhancement-side changes only (no analyzer re-run)
python3 enhancement_auditor.py regenerate --version vN --reuse-analysis audit_output/v8
python3 enhancement_auditor.py metrics --manifest vN
python3 enhancement_auditor.py judge --style vivid --manifest vN
python3 enhancement_auditor.py report --style vivid --manifest vN
```

Judge costs ~$15–25 per 50-image run with gpt-4.1 (API key from `.env`).
