#!/usr/bin/env python3
"""Test location detection quality across different models.

Randomly samples 50 images from ~/enhanced that have _analyzed.jpg files,
sends each to different Ollama models for location detection, and compares
the results against the ground truth from the existing JSON (which was
derived from description.txt or a prior LLM run).

Usage:
    # Test all available models
    python3 test_location_detection.py

    # Test specific models only
    python3 test_location_detection.py --models ministral-3:3b llama3.2-vision:11b

    # Use OpenAI for comparison
    python3 test_location_detection.py --openai

    # Adjust sample size
    python3 test_location_detection.py --sample 20
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import random
import sys
import time
from pathlib import Path

# --- Configuration -----------------------------------------------------------

ENHANCED_ROOT = Path.home() / "enhanced"
SAMPLE_SIZE = 50
TIMEOUT_PER_MODEL = 300  # seconds per image per model

# Models to test (must be pulled in Ollama first)
DEFAULT_MODELS = [
    "ministral-3:3b",        # current model (baseline)
    # Add more models here as you pull them:
    # "llama3.2-vision:11b",
    # "llava:13b",
    # "minicpm-v:8b",
]

# Location detection prompt (simplified version of the production prompt)
LOCATION_PROMPT = """You are a geographic location expert. Analyze this image and determine where it was taken.

Look for visual clues:
- Visible signs, text, license plates, street markers
- Architecture style and construction materials
- Vegetation and landscape type
- Road/infrastructure style
- Vehicle types and styles
- Famous landmarks or buildings

Respond in JSON format ONLY (no markdown, no explanation):
{
  "country": "country name or empty if unknown",
  "region": "state/province/region or empty if unknown",
  "city_or_area": "city or area name or empty if unknown",
  "confidence": 0-100,
  "reasoning": "brief explanation of what clues you used"
}

If you cannot determine the location, set confidence to 0 and leave fields empty.
Write all values in full — do NOT abbreviate or truncate."""


# --- Helpers -----------------------------------------------------------------

def find_sample_images(root: Path, n: int) -> list[Path]:
    """Find n random _analyzed.jpg files that have a corresponding JSON."""
    all_jpgs = sorted(root.rglob("*_analyzed.jpg"))
    # Filter to those that have a JSON with location data (ground truth)
    valid = []
    for jpg in all_jpgs:
        json_path = jpg.with_suffix(".json")
        if not json_path.exists():
            continue
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
            loc = data.get("location_detection", {})
            if isinstance(loc, dict) and loc.get("country"):
                valid.append(jpg)
        except Exception:
            continue

    if len(valid) < n:
        print(f"Warning: only found {len(valid)} images with ground truth, using all")
        n = len(valid)

    return random.sample(valid, n)


def encode_image(path: Path) -> str:
    """Base64-encode an image for the API."""
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def call_ollama(model: str, image_b64: str, host: str = "http://127.0.0.1:11434") -> dict:
    """Call an Ollama model for location detection."""
    import ollama

    client = ollama.Client(host=host, timeout=TIMEOUT_PER_MODEL)
    response = client.chat(
        model=model,
        messages=[{"role": "user", "content": LOCATION_PROMPT, "images": [image_b64]}],
        options={"num_ctx": 4096, "temperature": 0.3},
        keep_alive=0,
        format="json",
    )
    text = response["message"]["content"]
    return json.loads(text)


def call_openai(image_b64: str, model: str = "gpt-4o-mini") -> dict:
    """Call OpenAI for location detection."""
    from openai import OpenAI

    api_key = os.getenv("OPENAI_APIKEY", "")
    if not api_key:
        raise RuntimeError("OPENAI_APIKEY not set")

    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "user", "content": [
                {"type": "text", "text": LOCATION_PROMPT},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
            ]},
        ],
        max_tokens=512,
        temperature=0.3,
        response_format={"type": "json_object"},
    )
    text = response.choices[0].message.content
    return json.loads(text)


def normalize(s: str) -> str:
    """Normalize a string for comparison."""
    return s.strip().lower().replace("-", " ").replace(",", "")


def compare_locations(predicted: dict, ground_truth: dict) -> dict:
    """Compare predicted vs ground truth location."""
    gt_country = normalize(ground_truth.get("country", ""))
    gt_region = normalize(ground_truth.get("region", ""))
    gt_city = normalize(ground_truth.get("city_or_area", ""))

    pred_country = normalize(predicted.get("country", ""))
    pred_region = normalize(predicted.get("region", ""))
    pred_city = normalize(predicted.get("city_or_area", ""))

    # Check if any ground truth word appears in prediction (handles partial matches)
    def fuzzy_match(pred: str, gt: str) -> bool:
        if not gt or not pred:
            return False
        if pred == gt:
            return True
        # Check if the gt is a substring of pred or vice versa
        if gt in pred or pred in gt:
            return True
        # Check word overlap
        gt_words = set(gt.split())
        pred_words = set(pred.split())
        overlap = gt_words & pred_words
        return len(overlap) > 0 and len(overlap) / len(gt_words) > 0.5

    return {
        "country_match": fuzzy_match(pred_country, gt_country),
        "region_match": fuzzy_match(pred_region, gt_region) if gt_region else None,
        "city_match": fuzzy_match(pred_city, gt_city) if gt_city else None,
        "gt_country": ground_truth.get("country", ""),
        "gt_region": ground_truth.get("region", ""),
        "gt_city": ground_truth.get("city_or_area", ""),
        "pred_country": predicted.get("country", ""),
        "pred_region": predicted.get("region", ""),
        "pred_city": predicted.get("city_or_area", ""),
        "pred_confidence": predicted.get("confidence", 0),
        "pred_reasoning": predicted.get("reasoning", ""),
    }


# --- Main test ---------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Test location detection models")
    parser.add_argument("--sample", type=int, default=SAMPLE_SIZE, help="Number of images to test")
    parser.add_argument("--models", nargs="*", default=DEFAULT_MODELS, help="Ollama models to test")
    parser.add_argument("--openai", action="store_true", help="Also test with OpenAI gpt-4o-mini")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility")
    args = parser.parse_args()

    random.seed(args.seed)

    print(f"Finding {args.sample} random images with ground truth in {ENHANCED_ROOT}...")
    samples = find_sample_images(ENHANCED_ROOT, args.sample)
    print(f"Selected {len(samples)} images.\n")

    # Load ground truth for all samples
    ground_truths = []
    for jpg in samples:
        json_path = jpg.with_suffix(".json")
        data = json.loads(json_path.read_text(encoding="utf-8"))
        loc = data.get("location_detection", {})
        ground_truths.append(loc)

    # Print ground truth summary
    print("Ground truth locations:")
    for i, (jpg, gt) in enumerate(zip(samples, ground_truths)):
        print(f"  [{i+1:2d}] {jpg.parent.name}/{jpg.name}")
        print(f"       -> {gt.get('country', '?')}, {gt.get('region', '?')}, {gt.get('city_or_area', '?')}")
    print()

    # Test each model
    all_models = list(args.models)
    if args.openai:
        all_models.append("gpt-4o-mini (OpenAI)")

    results: dict[str, list[dict]] = {m: [] for m in all_models}

    for model in all_models:
        print(f"\n{'='*60}")
        print(f"Testing: {model}")
        print(f"{'='*60}")

        for i, (jpg, gt) in enumerate(zip(samples, ground_truths)):
            rel = f"{jpg.parent.name}/{jpg.name}"
            print(f"  [{i+1}/{len(samples)}] {rel}...", end=" ", flush=True)

            try:
                image_b64 = encode_image(jpg)

                if "OpenAI" in model:
                    pred = call_openai(image_b64)
                else:
                    pred = call_ollama(model, image_b64)

                comparison = compare_locations(pred, gt)
                results[model].append(comparison)

                match_str = "✓" if comparison["country_match"] else "✗"
                print(f"{match_str} {pred.get('country', '?')}, {pred.get('city_or_area', '?')} (conf: {pred.get('confidence', 0)})")

            except Exception as e:
                print(f"ERROR: {e}")
                results[model].append({
                    "country_match": False,
                    "region_match": None,
                    "city_match": None,
                    "gt_country": gt.get("country", ""),
                    "gt_region": gt.get("region", ""),
                    "gt_city": gt.get("city_or_area", ""),
                    "pred_country": "",
                    "pred_region": "",
                    "pred_city": "",
                    "pred_confidence": 0,
                    "pred_reasoning": f"ERROR: {e}",
                })

    # --- Summary -------------------------------------------------------------
    print(f"\n\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}\n")
    print(f"{'Model':<30} {'Country':>10} {'Region':>10} {'City':>10} {'Avg Conf':>10}")
    print("-" * 70)

    for model in all_models:
        model_results = results[model]
        country_correct = sum(1 for r in model_results if r["country_match"])
        region_correct = sum(1 for r in model_results if r["region_match"])
        city_correct = sum(1 for r in model_results if r["city_match"])
        avg_conf = sum(r["pred_confidence"] for r in model_results) / len(model_results)

        n = len(model_results)
        print(f"{model:<30} {country_correct:>4}/{n} ({country_correct/n*100:.0f}%)  "
              f"{region_correct:>4}/{n} ({region_correct/n*100:.0f}%)  "
              f"{city_correct:>4}/{n} ({city_correct/n*100:.0f}%)  "
              f"{avg_conf:>5.0f}")

    # Print detailed mismatches for each model
    for model in all_models:
        model_results = results[model]
        mismatches = [(i, r) for i, r in enumerate(model_results) if not r["country_match"]]
        if mismatches:
            print(f"\n--- {model}: {len(mismatches)} mismatches ---")
            for i, r in mismatches:
                print(f"  [{i+1}] GT: {r['gt_country']}, {r['gt_city']}")
                print(f"       Pred: {r['pred_country']}, {r['pred_city']} (conf: {r['pred_confidence']})")
                if r["pred_reasoning"]:
                    print(f"       Reason: {r['pred_reasoning'][:100]}")


if __name__ == "__main__":
    main()
