#!/usr/bin/env python3
"""Enhancement Quality Auditor — standalone, read-only.

Audits whether the enhancement pipeline produces the best possible results:
  1. Stratified sample of 50 images from ~/enhanced (by restoration profile × decade)
  2. Objective image metrics for every variant (local, free)
  3. LLM judge (OpenAI Vision, gpt-4.1) — blind multi-way ranking + recommendation audit
  4. Markdown summary report + HTML gallery in audit_output/

The script NEVER modifies anything in ~/enhanced. All outputs go to audit_output/.

Usage:
    python3 enhancement_auditor.py sample                    # build sample manifest only
    python3 enhancement_auditor.py metrics                 # objective metrics only
    python3 enhancement_auditor.py judge --limit 2          # LLM judge on 2 images (smoke test)
    python3 enhancement_auditor.py judge                    # LLM judge on full sample
    python3 enhancement_auditor.py report                   # generate report + HTML gallery
    python3 enhancement_auditor.py all                      # sample + metrics + judge + report
    python3 enhancement_auditor.py all --sample-size 50 --seed 42

Resumable: per-image judge results are saved immediately; re-running skips done images.
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import os
import random
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, median
from urllib.parse import quote

# ── Configuration ────────────────────────────────────────────────────────────

ENHANCED_ROOT = Path.home() / "enhanced"
OUTPUT_DIR = Path(__file__).parent / "audit_output"
JUDGE_MODEL = "gpt-4.1"          # ≠ analyzer (gpt-4o-mini) → no self-agreement bias
MAX_DIMENSION = 1024             # downscale before sending to Vision API
JPEG_QUALITY = 85
SAMPLE_SIZE = 50
SEED = 42
REQUEST_DELAY_S = 1.0            # modest rate limiting between API calls

# Valid restoration profiles (from slide_restoration.py RESTORATION_PROFILES)
VALID_PROFILES = {
    "faded", "color_cast", "red_cast", "yellow_cast", "aged", "well_preserved",
}
# Rare profiles get guaranteed coverage in the stratified sample
RARE_PROFILES = ["red_cast", "color_cast", "yellow_cast", "faded"]
RARE_PER_PROFILE = 5             # images per rare profile (4 rare × 5 = 20)
DOMINANT_FILL = SAMPLE_SIZE - RARE_PER_PROFILE * len(RARE_PROFILES)  # 30

# ── Sampling ────────────────────────────────────────────────────────────────


def parse_decade(folder_name: str) -> str | None:
    """Extract decade like '1980s' from a folder name like '1985-10 Huwelijksreis Texel'."""
    m = re.search(r"\b(19[5-9]\d|20[0-2]\d)", folder_name)
    if not m:
        return None
    year = int(m.group(1))
    return f"{year // 10 * 10}s"


def find_candidates() -> list[dict]:
    """Find images with the complete set: analyzed.jpg + analyzed.json + enhanced.jpg + ≥1 restored."""
    candidates = []
    for jpg in ENHANCED_ROOT.rglob("*_analyzed.jpg"):
        stem_dir = jpg.parent
        stem = jpg.name[: -len("_analyzed.jpg")]
        json_path = stem_dir / f"{stem}_analyzed.json"
        enhanced_path = stem_dir / f"{stem}_enhanced.jpg"
        if not (json_path.exists() and enhanced_path.exists()):
            continue
        restored = {}
        for f in stem_dir.glob(f"{stem}_restored_*.jpg"):
            profile = f.name[len(stem) + len("_restored_"):-len(".jpg")]
            if profile in VALID_PROFILES:
                restored[profile] = f
        if not restored:
            continue
        try:
            analysis = json.loads(json_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        candidates.append({
            "original": str(jpg),
            "json": str(json_path),
            "enhanced": str(enhanced_path),
            "restored": {k: str(v) for k, v in restored.items()},
            "folder": stem_dir.name,
            "decade": parse_decade(stem_dir.name),
            "analysis": analysis,
        })
    return candidates


def build_sample(candidates: list[dict], size: int, seed: int) -> list[dict]:
    """Stratified sample: guaranteed rare-profile coverage + dominant fill across decades."""
    rng = random.Random(seed)

    def decade_key(c):
        return c["decade"] or "unknown"

    sample = []
    used = set()

    # 1. Rare profiles: RARE_PER_PROFILE each, spread across decades where possible
    for profile in RARE_PROFILES:
        pool = [c for c in candidates
                if profile in c["restored"] and id(c) not in used]
        if not pool:
            print(f"  Warning: no candidates for profile '{profile}'")
            continue
        # spread across decades: group by decade, round-robin
        by_decade = defaultdict(list)
        for c in pool:
            by_decade[decade_key(c)].append(c)
        for d in by_decade:
            rng.shuffle(by_decade[d])
        picked = []
        decades = sorted(by_decade)
        while len(picked) < min(RARE_PER_PROFILE, len(pool)):
            progressed = False
            for d in decades:
                if len(picked) >= RARE_PER_PROFILE:
                    break
                if by_decade[d]:
                    picked.append(by_decade[d].pop())
                    progressed = True
            if not progressed:
                break
        for c in picked:
            used.add(id(c))
        sample.extend(picked)

    # 2. Dominant profiles (well_preserved / aged): fill remainder, spread across decades
    dominant_pool = [c for c in candidates if id(c) not in used]
    by_decade = defaultdict(list)
    for c in dominant_pool:
        by_decade[decade_key(c)].append(c)
    for d in by_decade:
        rng.shuffle(by_decade[d])
    remaining = size - len(sample)
    decades = sorted(by_decade)
    picked = []
    while len(picked) < remaining and any(by_decade[d] for d in decades):
        for d in decades:
            if len(picked) >= remaining:
                break
            if by_decade[d]:
                picked.append(by_decade[d].pop())
    sample.extend(picked)

    rng.shuffle(sample)
    return sample[:size]


def cmd_sample(args) -> None:
    print(f"Scanning {ENHANCED_ROOT} for complete image sets ...")
    candidates = find_candidates()
    print(f"Found {len(candidates)} complete sets")
    sample = build_sample(candidates, args.sample_size, args.seed)
    profile_counts = Counter(
        p for c in sample for p in c["restored"]
    )
    decade_counts = Counter(c["decade"] or "unknown" for c in sample)
    print(f"Sample: {len(sample)} images")
    print(f"  Profiles covered: {dict(profile_counts)}")
    print(f"  Decades covered:  {dict(sorted(decade_counts.items()))}")
    manifest = {
        "seed": args.seed,
        "sample_size": args.sample_size,
        "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "images": [
            {
                "original": c["original"],
                "json": c["json"],
                "enhanced": c["enhanced"],
                "restored": c["restored"],
                "folder": c["folder"],
                "decade": c["decade"],
            }
            for c in sample
        ],
    }
    OUTPUT_DIR.mkdir(exist_ok=True)
    (OUTPUT_DIR / "sample_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"Manifest saved to {OUTPUT_DIR / 'sample_manifest.json'}")


def load_manifest(which: str = "sample") -> list[dict]:
    """Load a sample manifest.

    which="sample" → audit_output/sample_manifest.json (originals in ~/enhanced)
    which="vN"     → audit_output/vN/vN_manifest.json (regenerated variants)
    """
    if which == "sample":
        path = OUTPUT_DIR / "sample_manifest.json"
    else:
        path = OUTPUT_DIR / which / f"{which}_manifest.json"
    if not path.exists():
        sys.exit(f"No manifest found at {path}. Run 'sample' (or 'regenerate') first.")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    return manifest["images"]


# ── Objective metrics ────────────────────────────────────────────────────────


def compute_metrics(image_path: str) -> dict:
    """Objective image metrics. Raises on unreadable images."""
    from PIL import Image
    import numpy as np

    img = Image.open(image_path)
    if img.mode != "RGB":
        img = img.convert("RGB")
    # Downscale for speed — metrics are stable enough at this size
    img.thumbnail((1024, 1024))
    arr = np.asarray(img, dtype=np.float32)

    r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
    lum = 0.299 * r + 0.587 * g + 0.114 * b

    # Saturation: (max - min) / max per pixel (HSV-style)
    mx = arr.max(axis=2)
    mn = arr.min(axis=2)
    sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-6), 0.0)

    # Sharpness: variance of Laplacian (on luminance)
    lap = (
        -4 * lum
        + np.roll(lum, 1, 0) + np.roll(lum, -1, 0)
        + np.roll(lum, 1, 1) + np.roll(lum, -1, 1)
    )
    sharpness = float(lap.var())

    return {
        "mean_luminance": float(lum.mean()) / 255.0,
        "contrast_std": float(lum.std()) / 255.0,
        "highlight_clip_pct": float((lum >= 250).mean() * 100),
        "shadow_clip_pct": float((lum <= 5).mean() * 100),
        "mean_saturation": float(sat.mean()),
        "channel_balance": {
            "r": float(r.mean()), "g": float(g.mean()), "b": float(b.mean()),
        },
        "color_cast_ratio": float(
            (r.mean() - (g.mean() + b.mean()) / 2) / 255.0
        ),  # >0 red cast, <0 blue-ish
        "sharpness_lap_var": sharpness,
    }


def cmd_metrics(args) -> None:
    sample = load_manifest(args.manifest)
    print(f"Computing objective metrics for {len(sample)} images ...")
    results = {}
    for i, item in enumerate(sample, 1):
        stem = Path(item["original"]).name[: -len("_analyzed.jpg")]
        variants = {"original": item["original"], "enhanced": item["enhanced"]}
        variants.update(item["restored"])
        per_image = {}
        for vname, vpath in variants.items():
            try:
                per_image[vname] = compute_metrics(vpath)
            except Exception as e:
                per_image[vname] = {"error": str(e)}
        results[stem] = per_image
        print(f"  [{i}/{len(sample)}] {stem}")
    suffix = "" if args.manifest == "sample" else f"_{args.manifest}"
    out = OUTPUT_DIR / f"metrics{suffix}.json"
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"Metrics saved to {out}")


# ── LLM judge ───────────────────────────────────────────────────────────────

# Judge style: what the judge optimizes for when ranking variants.
STYLE_FAITHFUL = "faithful"   # naturalness/fidelity — default, critical of processing
STYLE_VIVID = "vivid"         # lively/punchy — values visible improvement

STYLE_GUIDANCE = {
    STYLE_FAITHFUL: (
        "Judge with a FIDELITY-FIRST mindset: the goal of photo restoration is a "
        "faithful, natural rendition. Preserve the character of the original capture "
        "(including natural warm evening/golden-hour light). Over-processed results "
        "(oversaturated, haloed, unnatural tones, removed atmosphere) must score LOW. "
        "A version that merely differs from the original is not better."
    ),
    STYLE_VIVID: (
        "Judge with a VIVIDNESS-FIRST mindset: the goal is a lively, engaging photo "
        "for a family album. Versions with pleasing brightness, color pop, and "
        "punch are BETTER, as long as they remain natural-looking (no halos, no "
        "blown highlights, no cartoonish oversaturation). A slightly enhanced, "
        "more vivid version can beat the original even if it deviates from the "
        "original capture's flat or muted look."
    ),
}

RANKING_PROMPT = """You are a critical photo-restoration judge. You will see {n} versions of the SAME photograph. They are provided in order: the FIRST image is version {labels_first}, the SECOND is {labels_second}, and so on. The labels are randomly assigned — you do NOT know which is the original or which pipeline produced each.

The photo is a scanned family photograph (possibly an old slide/dia). Judge each version STRICTLY on:
- exposure (no crushed shadows / blown highlights)
- color fidelity (natural skin tones, neutral whites/greys, no color casts)
- vibrancy (colorfulness and pop — how lively and engaging the colors are; a dull/muted image scores LOW here even if perfectly neutral)
- sharpness vs. noise/oversharpening artifacts (halos)
- absence of processing artifacts (banding, clipping, oversaturation)

NOTE: color fidelity and vibrancy are INDEPENDENT dimensions. A dull-but-neutral image can score high on fidelity and low on vibrancy; a colorful-but-cast image the reverse. Do not let one contaminate the other.

Score each version 1-10 on each dimension and overall, then rank them best-to-worst.

Respond in JSON ONLY:
{{
  "scores": {{
{score_fields}
  }},
  "ranking": ["<label_best>", "<label_second>", "..."],
  "winner": "<label>",
  "notes": "one or two sentences on key differences"
}}

For each label, "scores" contains: {{"exposure": 1-10, "color_fidelity": 1-10, "vibrancy": 1-10, "sharpness": 1-10, "artifacts": 1-10, "overall": 1-10}}.
{style_guidance}"""


def encode_for_api(image_path: str) -> str:
    """Downscale to ≤1024px JPEG and base64-encode for the Vision API."""
    from PIL import Image

    img = Image.open(image_path)
    if img.mode != "RGB":
        img = img.convert("RGB")
    img.thumbnail((MAX_DIMENSION, MAX_DIMENSION))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=JPEG_QUALITY)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def call_judge(client, prompt: str, images: list[str]) -> str:
    """Call the judge model with prompt + images. Returns raw text."""
    content = [{"type": "text", "text": prompt}]
    for b64 in images:
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
        })
    response = client.chat.completions.create(
        model=JUDGE_MODEL,
        max_tokens=2000,
        messages=[
            {"role": "system", "content": "You are a strict, unbiased image-quality judge. Respond in JSON only."},
            {"role": "user", "content": content},
        ],
    )
    return response.choices[0].message.content


def parse_json_loose(text: str) -> dict:
    """Extract JSON object from a model response (handles code fences etc.)."""
    text = text.strip()
    # Strip markdown code fences if present
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    m = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not m:
        raise ValueError(f"No JSON found in response: {text[:200]}")
    return json.loads(m.group(0))


def judge_ranking(client, item: dict, rng: random.Random, style: str = STYLE_FAITHFUL) -> dict:
    """Blind multi-way ranking of all variants with randomized labels.

    Images are sent in blind-label order (A, B, C, ...) and the prompt tells the
    model that the first image is label A, the second B, etc. Variant names are
    never revealed to the model.
    """
    variants = {"original": item["original"], "enhanced": item["enhanced"]}
    variants.update(item["restored"])
    names = list(variants.keys())

    # Randomly assign blind labels to variants
    shuffled = names[:]
    rng.shuffle(shuffled)
    labels = [chr(ord("A") + i) for i in range(len(names))]
    label_map = dict(zip(shuffled, labels))          # variant name -> blind label
    label_to_variant = {v: k for k, v in label_map.items()}

    score_fields = ",\n".join(
        f'    "{label_map[n]}": {{"exposure": 0, "color_fidelity": 0, "vibrancy": 0, "sharpness": 0, "artifacts": 0, "overall": 0}}'
        for n in names
    )
    prompt = RANKING_PROMPT.format(
        n=len(names),
        labels_first=labels[0],
        labels_second=labels[1] if len(labels) > 1 else labels[0],
        labels=", ".join(labels),
        score_fields=score_fields,
        style_guidance=STYLE_GUIDANCE[style],
    )
    # Send images in blind-label order (A first, then B, ...) so the model can
    # associate each image with its label.
    ordered_paths = [variants[label_to_variant[l]] for l in labels]
    raw = call_judge(client, prompt, [encode_for_api(p) for p in ordered_paths])
    # Persist the blind-label mapping so reports can translate A/B/C → variant names
    return {
        "raw": raw,
        "label_to_variant": label_to_variant,
        "variant_to_label": label_map,
    }


def judge_recommendations(client, item: dict) -> dict:
    """Audit the analysis JSON's recommendations + profiles against the original."""
    analysis = json.loads(Path(item["json"]).read_text(encoding="utf-8"))
    enhancement = analysis.get("enhancement", {})
    recs = enhancement.get("recommended_enhancements", [])
    profiles = analysis.get("slide_profiles", [])

    prompt = f"""You are auditing an automated photo-enhancement pipeline. Below is the ORIGINAL scanned photograph, followed by the enhancement recommendations the pipeline's analyzer produced, and the restoration profiles it selected.

=== ANALYZER'S RECOMMENDATIONS (DSL format) ===
{json.dumps(recs, indent=2)}

=== ANALYZER'S SLIDE PROFILES (with confidence) ===
{json.dumps(profiles, indent=2)}

=== ANALYZER'S QUALITY ASSESSMENT ===
lighting: {enhancement.get('lighting_quality', 'n/a')}
color: {enhancement.get('color_analysis', 'n/a')}
sharpness: {enhancement.get('sharpness_clarity', 'n/a')}
contrast: {enhancement.get('contrast_level', 'n/a')}

Answer strictly in JSON:
{{
  "recommendations_appropriate": true/false,
  "recommendations_too": "strong" | "weak" | "appropriate",
  "profile_choice_correct": true/false,
  "correct_profile": "<what the profile should have been, or null>",
  "issues_found": ["..."],
  "suggested_recommendations": ["BRIGHTNESS: increase by X%", "..."],
  "reasoning": "one paragraph"
}}

Rules for suggested_recommendations (use ONLY the pipeline's DSL):
- BRIGHTNESS: increase/decrease by X%
- CONTRAST: increase/decrease by X%
- SATURATION: increase/decrease by X%
- SHARPNESS: increase/decrease by X%
- COLOR_TEMPERATURE: warm/cool by XK (X between 100 and 1500, e.g. "warm by 500K")
- UNSHARP_MASK: radius=Xpx, strength=X%, threshold=X
- SHADOWS: brighten/darken by X%
- HIGHLIGHTS: reduce/boost by X%
- VIBRANCE: increase/decrease by X%
- CLARITY: boost/reduce by X%
If the original needs no enhancement, return an empty list."""

    raw = call_judge(client, prompt, [encode_for_api(item["original"])])
    return {"raw": raw}


def cmd_judge(args) -> None:
    try:
        from openai import OpenAI
    except ImportError:
        sys.exit("openai package not installed. Run: pip install openai")

    from dotenv import load_dotenv
    load_dotenv()  # reads .env from cwd
    api_key = os.getenv("OPENAI_APIKEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        sys.exit("No OPENAI_APIKEY found in .env")
    client = OpenAI(api_key=api_key)

    which = args.manifest
    sample = load_manifest(which)
    if args.limit:
        sample = sample[: args.limit]
    style = args.style
    print(f"Judging {len(sample)} images with {JUDGE_MODEL} (style: {style}, manifest: {which}) ...")

    # Result file: judge_results[_style][_vN].jsonl
    name = "judge_results"
    if style != STYLE_FAITHFUL:
        name += f"_{style}"
    if which != "sample":
        name += f"_{which}"
    results_path = OUTPUT_DIR / f"{name}.jsonl"
    done = set()
    if results_path.exists():
        for line in results_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    done.add(json.loads(line)["stem"])
                except Exception:
                    pass
    print(f"  ({len(done)} already done, will be skipped)")

    rng = random.Random(args.seed)
    with results_path.open("a", encoding="utf-8") as out_f:
        for i, item in enumerate(sample, 1):
            stem = Path(item["original"]).name[: -len("_analyzed.jpg")]
            if stem in done:
                continue
            print(f"  [{i}/{len(sample)}] {stem} ...", flush=True)
            record = {"stem": stem, "folder": item["folder"], "decade": item["decade"],
                      "restored_profiles": list(item["restored"].keys()), "style": style}
            # Call 1: blind ranking
            try:
                rank = judge_ranking(client, item, rng, style=style)
                parsed = parse_json_loose(rank["raw"])
                # Map blind labels back to variant names
                l2v = rank["label_to_variant"]
                if "scores" in parsed:
                    parsed["scores"] = {l2v.get(k, k): v for k, v in parsed["scores"].items()}
                for field in ("ranking", "winner"):
                    if field in parsed:
                        if isinstance(parsed[field], str):
                            parsed[field] = l2v.get(parsed[field], parsed[field])
                        elif isinstance(parsed[field], list):
                            parsed[field] = [l2v.get(x, x) for x in parsed[field]]
                # Translate blind labels (A/B/C...) in free-text notes to variant names
                # NOTE: intentionally NOT auto-translated — the letter "A" is also an
                # English article, so regex replacement is unreliable. Instead the
                # label_legend is persisted and shown in the gallery/report.
                parsed["label_legend"] = dict(rank["variant_to_label"])  # variant -> blind label
                record["ranking"] = parsed
                record["ranking_ok"] = True
            except Exception as e:
                record["ranking"] = {"error": str(e)}
                record["ranking_ok"] = False
                print(f"    ranking failed: {e}")
            time.sleep(REQUEST_DELAY_S)

            # Call 2: recommendation audit
            try:
                rec = judge_recommendations(client, item)
                record["recommendation_audit"] = parse_json_loose(rec["raw"])
                record["recommendation_audit_ok"] = True
            except Exception as e:
                record["recommendation_audit"] = {"error": str(e)}
                record["recommendation_audit_ok"] = False
                print(f"    recommendation audit failed: {e}")
            time.sleep(REQUEST_DELAY_S)

            out_f.write(json.dumps(record, ensure_ascii=False) + "\n")
            out_f.flush()
    print(f"Judge results saved to {results_path}")


# ── Regeneration (re-run pipeline with NEW settings) ────────────────────────


def _regenerate_one(item: dict, out_dir: Path, provider: str | None,
                    reuse_from: Path | None = None) -> dict:
    """Re-analyze + re-enhance + re-restore one image with current settings.

    Writes <stem>_analyzed.json, _enhanced.jpg, _restored_<profile>.jpg into
    out_dir. Returns a dict with the new variant paths (never touches ~/enhanced).

    If reuse_from is given (a previous version's directory), the analysis JSON
    from there is reused and only enhancement/restoration is re-applied —
    useful for isolating enhancement-side changes (e.g. the cast-gate).
    """
    import yaml

    src = Path(item["original"])
    stem = src.name[: -len("_analyzed.jpg")]
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. Fresh analysis via the project's own pipeline (uses .env/config.yaml,
    #    including the Enhancement: <tag> description.txt mechanism)
    from src.picture_analyzer.cli.app import _analyze_with_provider
    from src.picture_analyzer.core.models import ImageData
    from src.picture_analyzer.data.prompt_loader import PromptLoader

    if reuse_from is not None:
        reused_json = reuse_from / f"{stem}_analyzed.json"
        payload = json.loads(reused_json.read_text(encoding="utf-8"))
        print(f"    (reusing analysis from {reused_json.parent.name})")
    else:
        result = _analyze_with_provider(src, provider=provider)
        analysis = result.raw_response

        # Normalise into the legacy dict shape the enhancer/restorer expect
        payload = dict(analysis)
        payload.setdefault("enhancement", {})
        if result.enhancement_recommendations:
            recs = payload["enhancement"].get("recommended_enhancements")
            if not recs:
                payload["enhancement"]["recommended_enhancements"] = [
                    e.raw_text for e in result.enhancement_recommendations
                ]
        if result.slide_profile:
            payload["slide_profiles"] = [
                {"profile": result.slide_profile.profile_name,
                 "confidence": result.slide_profile.confidence}
            ]

    json_path = out_dir / f"{stem}_analyzed.json"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    # 2. Copy source image (untouched original) into v2 tree
    v2_original = out_dir / f"{stem}_analyzed.jpg"
    if not v2_original.exists():
        import shutil
        shutil.copy2(src, v2_original)

    # 3. AI-recommendation enhancement (SmartEnhancer, new prompts)
    from picture_enhancer import SmartEnhancer
    enhanced_path = out_dir / f"{stem}_enhanced.jpg"
    SmartEnhancer().enhance_from_analysis(
        str(v2_original), payload["enhancement"], str(enhanced_path)
    )

    # 4. Profile restoration (SlideRestoration, new tuned profiles)
    from slide_restoration import SlideRestoration
    valid = set(SlideRestoration.RESTORATION_PROFILES.keys())
    restored = {}
    for p in payload.get("slide_profiles", []):
        name = p.get("profile") if isinstance(p, dict) else p
        if name not in valid:
            continue
        restored_path = out_dir / f"{stem}_restored_{name}.jpg"
        SlideRestoration.restore_slide(
            str(v2_original), profile=name, output_path=str(restored_path),
            denoise=True, despeckle=True,
        )
        restored[name] = str(restored_path)

    return {
        "original": str(v2_original),
        "json": str(json_path),
        "enhanced": str(enhanced_path) if enhanced_path.exists() else None,
        "restored": restored,
        "folder": item["folder"],
        "decade": item["decade"],
    }


def cmd_regenerate(args) -> None:
    """Regenerate enhanced/restored variants for the sample with NEW settings."""
    sample = load_manifest()
    if args.limit:
        sample = sample[: args.limit]
    version = args.version
    out_dir = OUTPUT_DIR / version
    reuse_from = Path(args.reuse_analysis) if args.reuse_analysis else None
    if reuse_from is not None:
        print(f"Reusing analysis JSONs from {reuse_from} (enhancement-side changes only)")
    print(f"Regenerating {len(sample)} images with NEW settings → {out_dir}")

    # Import path setup: project root must be importable
    sys.path.insert(0, str(Path(__file__).parent))

    done_path = out_dir / f"{version}_manifest.json"
    done = {}
    if done_path.exists():
        done = {m["original"]: m for m in json.loads(done_path.read_text())["images"]}

    new_manifest = list(done.values())
    for i, item in enumerate(sample, 1):
        stem = Path(item["original"]).name[: -len("_analyzed.jpg")]
        if item["original"] in done:
            print(f"  [{i}/{len(sample)}] {stem} — already done, skipping")
            continue
        print(f"  [{i}/{len(sample)}] {stem} ...", flush=True)
        try:
            entry = _regenerate_one(item, out_dir, args.provider, reuse_from=reuse_from)
            if not entry["enhanced"]:
                print(f"    ⚠ no enhanced output produced")
            new_manifest.append(entry)
        except Exception as e:
            import traceback
            print(f"    ✗ failed: {e}")
            traceback.print_exc()
        # Save progress incrementally so the run is resumable
        done_path.write_text(
            json.dumps({"images": new_manifest}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    print(f"{version} manifest saved to {done_path} ({len(new_manifest)} images)")


# ── Report ──────────────────────────────────────────────────────────────────


def load_judge_results(style: str = STYLE_FAITHFUL, which: str = "sample") -> list[dict]:
    name = "judge_results"
    if style != STYLE_FAITHFUL:
        name += f"_{style}"
    if which != "sample":
        name += f"_{which}"
    path = OUTPUT_DIR / f"{name}.jsonl"
    if not path.exists():
        sys.exit(f"No judge results found at {path}. Run 'judge --style {style} --manifest {which}' first.")
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def load_metrics() -> dict:
    path = OUTPUT_DIR / "metrics.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def cmd_report(args) -> None:
    style = args.style
    which = args.manifest
    results = load_judge_results(style, which)
    metrics = load_metrics()
    manifest = load_manifest(which)
    print(f"Generating report from {len(results)} judged images (style: {style}, manifest: {which}) ...")

    # ── Aggregate win rates ──
    wins = Counter()
    appearances = Counter()
    overall_scores = defaultdict(list)
    for r in results:
        rank = r.get("ranking", {})
        if not r.get("ranking_ok"):
            continue
        winner = rank.get("winner")
        if winner:
            wins[winner] += 1
        for v in rank.get("scores", {}):
            appearances[v] += 1
            sc = rank["scores"][v].get("overall")
            if isinstance(sc, (int, float)):
                overall_scores[v].append(sc)

    # ── Recommendation audit aggregates ──
    rec_too = Counter()
    profile_correct = Counter()
    n_rec_audits = 0
    for r in results:
        audit = r.get("recommendation_audit", {})
        if not r.get("recommendation_audit_ok"):
            continue
        n_rec_audits += 1
        rec_too[audit.get("recommendations_too", "unknown")] += 1
        profile_correct[bool(audit.get("profile_choice_correct"))] += 1

    # ── Per-profile-type wins ──
    profile_type_wins = defaultdict(Counter)
    for r in results:
        rank = r.get("ranking", {})
        if not r.get("ranking_ok") or not rank.get("winner"):
            continue
        for p in r.get("restored_profiles", []):
            profile_type_wins[p][rank["winner"]] += 1

    lines = []
    lines.append("# Enhancement Quality Audit Report")
    lines.append("")
    lines.append(f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"Sample: {len(results)} judged images (of {len(manifest)} in manifest)")
    lines.append(f"Judge model: {JUDGE_MODEL}")
    lines.append(f"Judge style: {style} "
                 f"({'naturalness/fidelity' if style == STYLE_FAITHFUL else 'lively/punchy family-album look'})")
    lines.append("")

    lines.append("## 1. Blind ranking — win rates")
    lines.append("")
    lines.append("| Variant | Wins | Appearances | Win rate | Avg overall score |")
    lines.append("|---------|------|-------------|----------|-------------------|")
    for v in sorted(appearances, key=lambda x: -wins.get(x, 0)):
        wr = wins.get(v, 0) / appearances[v] * 100 if appearances[v] else 0
        avg = mean(overall_scores[v]) if overall_scores[v] else float("nan")
        lines.append(f"| {v} | {wins.get(v, 0)} | {appearances[v]} | {wr:.0f}% | {avg:.1f} |")
    lines.append("")

    lines.append("## 2. Recommendation audit")
    lines.append("")
    lines.append(f"- Audited: {n_rec_audits} images")
    lines.append(f"- Recommendations judged: {dict(rec_too)}")
    lines.append(f"- Profile choice correct: {dict(profile_correct)}")
    lines.append("")

    lines.append("## 3. Wins by restoration profile type")
    lines.append("")
    for p, w in sorted(profile_type_wins.items()):
        total = sum(w.values())
        lines.append(f"### Images with profile `{p}` ({total} images)")
        lines.append("")
        lines.append("| Winning variant | Count |")
        lines.append("|-----------------|-------|")
        for v, c in w.most_common():
            lines.append(f"| {v} | {c} |")
        lines.append("")

    # ── Objective metric deltas for winners vs losers ──
    if metrics:
        lines.append("## 4. Objective metrics — winners vs. rest")
        lines.append("")
        lines.append("Average metric deltas vs. original, grouped by whether the variant "
                     "won its image's blind ranking:")
        lines.append("")
        lines.append("| Variant | Role | Δlum | Δcontrast | Δsat | Δsharp |")
        lines.append("|---------|------|------|-----------|------|--------|")
        winner_deltas = defaultdict(list)
        loser_deltas = defaultdict(list)
        for r in results:
            rank = r.get("ranking", {})
            if not r.get("ranking_ok") or not rank.get("winner"):
                continue
            m = metrics.get(r["stem"], {})
            orig = m.get("original", {})
            if "error" in orig:
                continue
            for v, vm in m.items():
                if v == "original" or "error" in vm:
                    continue
                d = (
                    vm["mean_luminance"] - orig["mean_luminance"],
                    vm["contrast_std"] - orig["contrast_std"],
                    vm["mean_saturation"] - orig["mean_saturation"],
                    vm["sharpness_lap_var"] - orig["sharpness_lap_var"],
                )
                (winner_deltas if v == rank["winner"] else loser_deltas)[v].append(d)
        for v in sorted(set(list(winner_deltas) + list(loser_deltas))):
            for role, store in (("winner", winner_deltas), ("other", loser_deltas)):
                ds = store.get(v, [])
                if not ds:
                    continue
                dl, dc, dsat, dsh = (mean(x[i] for x in ds) for i in range(4))
                lines.append(
                    f"| {v} | {role} | {dl:+.3f} | {dc:+.3f} | {dsat:+.3f} | {dsh:+.0f} |"
                )
        lines.append("")

    # ── Notable failures ──
    lines.append("## 5. Notable findings")
    lines.append("")
    for r in results:
        rank = r.get("ranking", {})
        if r.get("ranking_ok") and rank.get("winner") == "original":
            lines.append(f"- ⚠️ **Original won** over all enhanced/restored variants: "
                         f"`{r['stem']}` ({r['folder']})")
    for r in results:
        audit = r.get("recommendation_audit", {})
        if r.get("recommendation_audit_ok") and audit.get("issues_found"):
            issues = "; ".join(audit["issues_found"][:3])
            lines.append(f"- `{r['stem']}` ({r['folder']}): {issues}")
    lines.append("")

    report_path = OUTPUT_DIR / (
        ("audit_report.md" if style == STYLE_FAITHFUL else f"audit_report_{style}.md")
        if which == "sample" else
        (f"audit_report_{which}.md" if style == STYLE_FAITHFUL else f"audit_report_{style}_{which}.md")
    )
    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Report saved to {report_path}")

    generate_html_gallery(results, metrics, manifest, style, which)


def generate_html_gallery(results: list[dict], metrics: dict, manifest: list[dict],
                          style: str = STYLE_FAITHFUL, which: str = "sample") -> None:
    """Side-by-side HTML gallery with verdicts for human spot-checking."""
    items_by_stem = {
        Path(m["original"]).name[: -len("_analyzed.jpg")]: m for m in manifest
    }
    html = ["<!DOCTYPE html><html><head><meta charset='utf-8'>",
            "<title>Enhancement Audit Gallery</title>",
            "<style>",
            "body{font-family:sans-serif;background:#1e1e1e;color:#ddd;margin:20px}",
            "h2{border-bottom:1px solid #555;padding-bottom:4px}",
            ".imgrow{display:flex;flex-wrap:wrap;gap:10px}",
            ".card{background:#2a2a2a;padding:8px;border-radius:6px;max-width:340px}",
            ".card img{max-width:320px;max-height:240px;display:block}",
            ".card.winner{outline:3px solid #4caf50}",
            ".card.original{outline:3px solid #888}",
            ".label{font-weight:bold;margin-bottom:4px}",
            ".legend{font-size:0.9em;color:#ffcc80;margin-bottom:6px}",
            ".scores{font-size:0.85em;color:#aaa}",
            ".notes{font-size:0.85em;color:#8bc34a;margin-top:6px}",
            "</style></head><body>",
            "<h1>Enhancement Audit Gallery</h1>"]
    for r in results:
        stem = r["stem"]
        item = items_by_stem.get(stem)
        if not item:
            continue
        rank = r.get("ranking", {})
        scores = rank.get("scores", {}) if r.get("ranking_ok") else {}
        winner = rank.get("winner")
        legend = rank.get("label_legend", {})  # variant name -> blind label (A/B/C...)
        html.append(f"<h2>{stem} <small>({r.get('folder', '')})</small></h2>")
        if legend:
            legend_txt = " · ".join(
                f"{label} = {vname}" for vname, label in sorted(legend.items(), key=lambda kv: kv[1])
            )
            html.append(f"<div class='legend'>Blind labels: {legend_txt}</div>")
        html.append("<div class='imgrow'>")
        variants = {"original": item["original"], "enhanced": item["enhanced"]}
        variants.update(item["restored"])
        for vname, vpath in variants.items():
            cls = "card winner" if vname == winner else ("card original" if vname == "original" else "card")
            sc = scores.get(vname, {})
            sc_txt = " · ".join(
                f"{k}:{v}" for k, v in sc.items()
                if isinstance(v, (int, float))
            ) if sc else ""
            label = legend.get(vname)
            label_txt = f" [{label}]" if label else ""
            # Use file:// URI for local viewing (quote spaces etc.)
            uri = "file://" + quote(str(Path(vpath).resolve()))
            html.append(
                f"<div class='{cls}'><div class='label'>{vname}{label_txt}"
                + (" 🏆" if vname == winner else "") + "</div>"
                f"<img src='{uri}' loading='lazy'>"
                f"<div class='scores'>{sc_txt}</div></div>"
            )
        html.append("</div>")
        audit = r.get("recommendation_audit", {})
        if r.get("recommendation_audit_ok"):
            html.append(f"<div class='notes'>Audit: recommendations "
                        f"{audit.get('recommendations_too', '?')} · profile correct: "
                        f"{audit.get('profile_choice_correct', '?')} — "
                        f"{audit.get('reasoning', '')}</div>")
        if rank.get("notes"):
            html.append(f"<div class='notes'>Judge: {rank['notes']}</div>")
    html.append("</body></html>")
    out = OUTPUT_DIR / (
        ("audit_gallery.html" if style == STYLE_FAITHFUL else f"audit_gallery_{style}.html")
        if which == "sample" else
        (f"audit_gallery_{which}.html" if style == STYLE_FAITHFUL else f"audit_gallery_{style}_{which}.html")
    )
    out.write_text("\n".join(html), encoding="utf-8")
    print(f"HTML gallery saved to {out}")


# ── Compare judging styles ───────────────────────────────────────────────────


def cmd_compare(args) -> None:
    """Compare faithful vs vivid judge verdicts on the same sample."""
    faithful = {r["stem"]: r for r in load_judge_results(STYLE_FAITHFUL)}
    vivid = {r["stem"]: r for r in load_judge_results(STYLE_VIVID)}
    common = sorted(set(faithful) & set(vivid))
    if not common:
        sys.exit("No overlapping judged images between the two styles.")

    print(f"Comparing {len(common)} images judged under both styles\n")

    def winner_of(rec):
        return rec.get("ranking", {}).get("winner") if rec.get("ranking_ok") else None

    flips = Counter()          # (faithful_winner, vivid_winner) transitions
    for stem in common:
        fw, vw = winner_of(faithful[stem]), winner_of(vivid[stem])
        if fw and vw:
            flips[(fw, vw)] += 1

    # Win rates per style
    for style_name, store in ((STYLE_FAITHFUL, faithful), (STYLE_VIVID, vivid)):
        wins = Counter()
        apps = Counter()
        for stem in common:
            w = winner_of(store[stem])
            rank = store[stem].get("ranking", {})
            for v in rank.get("scores", {}):
                apps[v] += 1
            if w:
                wins[w] += 1
        print(f"── Style: {style_name} ──")
        for v in sorted(apps, key=lambda x: -wins.get(x, 0)):
            wr = wins.get(v, 0) / apps[v] * 100 if apps[v] else 0
            print(f"  {v:16s} {wins.get(v, 0):3d}/{apps[v]:3d}  ({wr:.0f}%)")
        print()

    changed = sum(1 for (fw, vw), c in flips.items() if fw != vw)
    print(f"Verdict changed on {changed}/{len(common)} images when switching to vivid judging:")
    for (fw, vw), c in sorted(flips.items(), key=lambda kv: -kv[1]):
        marker = "" if fw == vw else " ← changed"
        print(f"  {fw:16s} → {vw:16s}  {c:3d} image(s){marker}")

    # Save detailed comparison
    out = OUTPUT_DIR / "style_comparison.json"
    detail = [
        {
            "stem": stem,
            "faithful_winner": winner_of(faithful[stem]),
            "vivid_winner": winner_of(vivid[stem]),
            "faithful_scores": faithful[stem].get("ranking", {}).get("scores", {}),
            "vivid_scores": vivid[stem].get("ranking", {}).get("scores", {}),
        }
        for stem in common
    ]
    out.write_text(json.dumps(detail, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nDetailed comparison saved to {out}")


# ── Score table ─────────────────────────────────────────────────────────────


def cmd_scores(args) -> None:
    """Write a per-image markdown table: sub-scores + accumulated sum per variant."""
    style = args.style
    which = args.manifest
    results = load_judge_results(style, which)
    # Detect score format (new: color_fidelity+vibrancy, old: color)
    sample_scores = next(
        (r.get("ranking", {}).get("scores", {}) for r in results if r.get("ranking_ok")), {}
    )
    new_format = "color_fidelity" in next(iter(sample_scores.values()), {}) if sample_scores else False
    sub_headers = (
        ["Exp", "Fid", "Vib", "Sharp", "Artif"] if new_format
        else ["Exp", "Col", "Sharp", "Artif"]
    )
    max_sum = 50 if new_format else 40
    lines = [
        "# Judge Score Table",
        "",
        f"Style: {style} · manifest: {which} · judge: {JUDGE_MODEL}",
        "",
        f"Accumulated = sum of the sub-scores ({' + '.join(sub_headers)}, max {max_sum}).",
        "`overall` is the judge's own separate 1-10 verdict. 🏆 = judge's winner.",
        "",
        "| Image | Variant | " + " | ".join(sub_headers) + " | **Sum** | Overall |",
        "|-------|---------|" + "|".join(["-----"] * len(sub_headers)) + "|---------|---------|",
    ]
    for r in results:
        rank = r.get("ranking", {})
        if not r.get("ranking_ok"):
            continue
        winner = rank.get("winner")
        scores = rank.get("scores", {})
        # Sub-score keys: new format has color_fidelity+vibrancy, old has color
        def subkeys(sc):
            if "color_fidelity" in sc or "vibrancy" in sc:
                return ("exposure", "color_fidelity", "vibrancy", "sharpness", "artifacts")
            return ("exposure", "color", "sharpness", "artifacts")

        # Sort variants: winner first, then by sum descending
        def sort_key(item):
            v, sc = item
            sub = [sc.get(k) for k in subkeys(sc)]
            s = sum(x for x in sub if isinstance(x, (int, float)))
            return (v == winner, s)

        for v, sc in sorted(scores.items(), key=sort_key, reverse=True):
            keys = subkeys(sc)
            vals = [sc.get(k, "–") for k in keys]
            ov = sc.get("overall", "–")
            sub = [sc.get(k) for k in keys]
            if all(isinstance(x, (int, float)) for x in sub):
                s = f"**{sum(sub)}**"
            else:
                s = "–"
            trophy = " 🏆" if v == winner else ""
            lines.append(f"| {r['stem']} | {v}{trophy} | " + " | ".join(str(x) for x in vals) + f" | {s} | {ov} |")
        lines.append("| | | | | | | | |")

    name = "scores_table"
    if style != STYLE_FAITHFUL:
        name += f"_{style}"
    if which != "sample":
        name += f"_{which}"
    out = OUTPUT_DIR / f"{name}.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"Score table saved to {out}")


# ── Main ────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="Enhancement Quality Auditor")
    parser.add_argument("command", choices=["sample", "metrics", "judge", "report", "compare", "regenerate", "scores", "all"])
    parser.add_argument("--sample-size", type=int, default=SAMPLE_SIZE)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--limit", type=int, default=None, help="Judge only first N images")
    parser.add_argument(
        "--style", choices=[STYLE_FAITHFUL, STYLE_VIVID], default=STYLE_FAITHFUL,
        help="Judge style: faithful (naturalness-first, default) or vivid (lively family-album look)",
    )
    parser.add_argument(
        "--provider", default=None,
        help="Analyzer provider for regenerate (default: config value, e.g. ollama)",
    )
    parser.add_argument(
        "--manifest", default="sample",
        help="Which manifest to use: sample (originals in ~/enhanced) or a version dir like v2/v3/v4 (regenerated)",
    )
    parser.add_argument(
        "--version", default="v3",
        help="Output version directory for regenerate (default: v3)",
    )
    parser.add_argument(
        "--reuse-analysis", default=None, metavar="DIR",
        help="Reuse analysis JSONs from a previous version dir (e.g. audit_output/v3) — only re-apply enhancement/restoration",
    )
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(exist_ok=True)

    if args.command == "sample":
        cmd_sample(args)
    elif args.command == "metrics":
        cmd_metrics(args)
    elif args.command == "judge":
        cmd_judge(args)
    elif args.command == "report":
        cmd_report(args)
    elif args.command == "compare":
        cmd_compare(args)
    elif args.command == "regenerate":
        cmd_regenerate(args)
    elif args.command == "scores":
        cmd_scores(args)
    elif args.command == "all":
        cmd_sample(args)
        cmd_metrics(args)
        cmd_judge(args)
        cmd_report(args)


if __name__ == "__main__":
    main()
