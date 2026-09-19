#!/usr/bin/env python3
"""Two-stage location detection test: LLM filter + GeoCLIP.

Stage 1: Use ministral-3:3b (or OpenAI) to classify each image as
  "landmark" or "not landmark" — i.e., does this image contain recognizable
  geographic features (famous buildings, landscapes, street scenes, signs)?

Stage 2: For images classified as "landmark", run GeoCLIP to predict GPS.
  For images classified as "not landmark", skip GeoCLIP (no point).

Then compare results against ground truth from existing _analyzed.json files.

Usage:
    python3 test_geoclip_filtered.py --sample 50
    python3 test_geoclip_filtered.py --sample 50 --use-openai  # use gpt-4o-mini for filter
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

ENHANCED_ROOT = Path.home() / "enhanced"
FOTOS_ROOT = Path.home() / "fotos"

# LLM filter prompt — asks the model to classify whether the image
# has geographic clues that GeoCLIP could work with
FILTER_PROMPT = """Look at this image and answer: could a geolocation AI determine where this photo was taken?

Consider these POSITIVE signals:
- Famous landmarks or monuments (Eiffel Tower, Colosseum, Big Ben, etc.)
- Distinctive architecture (Dutch canal houses, Alpine chalets, Mediterranean villages)
- Street scenes with visible signs, license plates, or road markers
- Distinctive landscapes (mountains, coastlines, deserts, forests)
- Public spaces, city squares, tourist attractions
- Infrastructure (bridges, dams, airports, train stations)

Consider these NEGATIVE signals (GeoCLIP will NOT be able to locate these):
- Indoor photos (living rooms, kitchens, classrooms)
- Close-up portraits or group photos
- Backyards, gardens, or generic suburban scenes
- Blurry or dark photos
- Scanned old slides with poor quality
- Photos of objects, food, or documents

Respond in JSON ONLY:
{
  "is_landmark": true/false,
  "confidence": 0-100,
  "reason": "one sentence explaining what geographic clues are visible, or why there are none"
}"""


def find_sample_images(root: Path, n: int) -> list[tuple[Path, dict]]:
    """Find n random _analyzed.jpg files with ground truth location data."""
    all_jpgs = sorted(root.rglob("*_analyzed.jpg"))
    valid = []
    for jpg in all_jpgs:
        json_path = jpg.with_suffix(".json")
        if not json_path.exists():
            continue
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
            loc = data.get("location_detection", {})
            gps = data.get("gps_coordinates", {})
            if isinstance(loc, dict) and loc.get("country"):
                valid.append((jpg, {"loc": loc, "gps": gps}))
        except Exception:
            continue
    if len(valid) < n:
        print(f"Warning: only found {len(valid)} images with ground truth, using all")
        n = len(valid)
    return random.sample(valid, n)


def encode_image(path: Path) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def haversine_km(lat1, lon1, lat2, lon2):
    import math
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1))*math.cos(math.radians(lat2))*math.sin(dlon/2)**2
    return 2 * R * math.asin(math.sqrt(a))


def reverse_geocode(lat, lon):
    import requests
    time.sleep(1.1)
    try:
        resp = requests.get(
            "https://nominatim.openstreetmap.org/reverse",
            params={"lat": lat, "lon": lon, "format": "json", "addressdetails": 1, "zoom": 10},
            headers={"User-Agent": "picture-analyzer-test/1.0"},
            timeout=10,
        )
        data = resp.json()
        addr = data.get("address", {})
        return {
            "country": addr.get("country", ""),
            "city": addr.get("city", addr.get("town", addr.get("village", ""))),
        }
    except Exception as e:
        return {"country": "", "city": f"ERROR: {e}"}


def normalize(s):
    return s.strip().lower().replace("-", " ").replace(",", "")


def fuzzy_match(pred, gt):
    if not gt or not pred:
        return False
    pred, gt = normalize(pred), normalize(gt)
    if pred == gt:
        return True
    if gt in pred or pred in gt:
        return True
    gt_words = set(gt.split())
    pred_words = set(pred.split())
    overlap = gt_words & pred_words
    return len(overlap) > 0 and len(overlap) / len(gt_words) > 0.5


# --- Stage 1: LLM filter ----------------------------------------------------

def llm_filter_ollama(image_b64, model="ministral-3:3b", host="http://127.0.0.1:11434"):
    """Use Ollama to classify if image has landmark/geographic content."""
    import ollama
    client = ollama.Client(host=host, timeout=300)
    response = client.chat(
        model=model,
        messages=[{"role": "user", "content": FILTER_PROMPT, "images": [image_b64]}],
        options={"num_ctx": 4096, "temperature": 0.3},
        keep_alive=0,
        format="json",
    )
    return json.loads(response["message"]["content"])


def llm_filter_openai(image_b64):
    """Use OpenAI gpt-4o-mini to classify if image has landmark/geographic content."""
    from openai import OpenAI
    api_key = os.getenv("OPENAI_APIKEY", "")
    if not api_key:
        raise RuntimeError("OPENAI_APIKEY not set")
    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": [
            {"type": "text", "text": FILTER_PROMPT},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
        ]}],
        max_tokens=200,
        temperature=0.3,
        response_format={"type": "json_object"},
    )
    return json.loads(response.choices[0].message.content)


# --- Stage 2: GeoCLIP -------------------------------------------------------

def geoclip_predict(image_path, model):
    """Run GeoCLIP on an image, return (lat, lon, prob)."""
    top_gps, top_prob = model.predict(str(image_path), top_k=5)
    return float(top_gps[0][0]), float(top_gps[0][1]), float(top_prob[0])


# --- Main -------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Two-stage location detection test")
    parser.add_argument("--sample", type=int, default=50, help="Number of images to test")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--use-openai", action="store_true", help="Use OpenAI for LLM filter instead of Ollama")
    parser.add_argument("--skip-filter", action="store_true", help="Skip LLM filter, run GeoCLIP on all (for comparison)")
    args = parser.parse_args()

    random.seed(args.seed)

    print(f"Finding {args.sample} random images with ground truth in {ENHANCED_ROOT}...")
    samples = find_sample_images(ENHANCED_ROOT, args.sample)
    print(f"Selected {len(samples)} images.\n")

    # Load GeoCLIP
    print("Loading GeoCLIP model...")
    from geoclip import GeoCLIP
    geoclip_model = GeoCLIP()
    print("GeoCLIP loaded.\n")

    filter_name = "OpenAI gpt-4o-mini" if args.use_openai else "ministral-3:3b"
    if args.skip_filter:
        print("Mode: GeoCLIP only (no LLM filter)")
    else:
        print(f"Mode: LLM filter ({filter_name}) → GeoCLIP")
    print()

    results = []
    start_time = time.time()

    for i, (jpg, gt) in enumerate(samples):
        rel = f"{jpg.parent.name}/{jpg.name}"
        print(f"  [{i+1}/{len(samples)}] {rel}")

        gt_loc = gt["loc"]
        gt_gps = gt.get("gps", {})
        gt_lat = gt_gps.get("latitude")
        gt_lon = gt_gps.get("longitude")

        result = {
            "file": rel,
            "gt_country": gt_loc.get("country", ""),
            "gt_city": gt_loc.get("city_or_area", ""),
            "gt_lat": gt_lat,
            "gt_lon": gt_lon,
            "is_landmark": None,
            "filter_reason": "",
            "filter_confidence": 0,
            "geoclip_ran": False,
            "pred_lat": None,
            "pred_lon": None,
            "pred_prob": 0,
            "pred_country": "",
            "pred_city": "",
            "distance_km": None,
            "country_match": None,
        }

        # Stage 1: LLM filter
        if not args.skip_filter:
            try:
                image_b64 = encode_image(jpg)
                if args.use_openai:
                    filter_result = llm_filter_openai(image_b64)
                else:
                    filter_result = llm_filter_ollama(image_b64)

                result["is_landmark"] = filter_result.get("is_landmark", False)
                result["filter_reason"] = filter_result.get("reason", "")
                result["filter_confidence"] = filter_result.get("confidence", 0)

                tag = "LANDMARK" if result["is_landmark"] else "not landmark"
                print(f"       Filter: {tag} (conf: {result['filter_confidence']}) — {result['filter_reason'][:80]}")

            except Exception as e:
                print(f"       Filter: ERROR — {e}")
                result["filter_reason"] = f"ERROR: {e}"

        # Stage 2: GeoCLIP (only if landmark or skip_filter)
        should_run_geoclip = args.skip_filter or result["is_landmark"]
        if should_run_geoclip:
            result["geoclip_ran"] = True
            try:
                pred_lat, pred_lon, pred_prob = geoclip_predict(jpg, geoclip_model)
                result["pred_lat"] = pred_lat
                result["pred_lon"] = pred_lon
                result["pred_prob"] = pred_prob

                # Distance
                if gt_lat and gt_lon:
                    result["distance_km"] = haversine_km(gt_lat, gt_lon, pred_lat, pred_lon)

                # Reverse geocode
                place = reverse_geocode(pred_lat, pred_lon)
                result["pred_country"] = place.get("country", "")
                result["pred_city"] = place.get("city", "")
                result["country_match"] = fuzzy_match(place.get("country", ""), gt_loc.get("country", ""))

                dist_str = f" ({result['distance_km']:.0f}km)" if result["distance_km"] is not None else ""
                print(f"       GeoCLIP: {pred_lat:.4f}, {pred_lon:.4f} (p={pred_prob:.2f}) — {place.get('country', '?')}, {place.get('city', '?')}{dist_str}")

            except Exception as e:
                print(f"       GeoCLIP: ERROR — {e}")
                result["pred_country"] = f"ERROR: {e}"
        else:
            print(f"       GeoCLIP: skipped (not a landmark)")

        results.append(result)

    elapsed = time.time() - start_time

    # --- Summary ---
    print(f"\n\n{'='*70}")
    print("SUMMARY")
    print(f"{'='*70}\n")

    n = len(results)

    # Filter stats
    if not args.skip_filter:
        landmarks = [r for r in results if r["is_landmark"]]
        non_landmarks = [r for r in results if r["is_landmark"] is False]
        errors = [r for r in results if r["is_landmark"] is None]
        print(f"LLM Filter ({filter_name}):")
        print(f"  Landmarks (sent to GeoCLIP):  {len(landmarks)}/{n} ({len(landmarks)/n*100:.0f}%)")
        print(f"  Non-landmarks (skipped):      {len(non_landmarks)}/{n} ({len(non_landmarks)/n*100:.0f}%)")
        print(f"  Filter errors:                {len(errors)}/{n}")
        print()

    # GeoCLIP stats (only on images that were actually processed)
    geoclip_results = [r for r in results if r["geoclip_ran"]]
    geoclip_with_gps = [r for r in geoclip_results if r["distance_km"] is not None]

    if geoclip_with_gps:
        distances = [r["distance_km"] for r in geoclip_with_gps]
        within_25 = sum(1 for d in distances if d <= 25)
        within_100 = sum(1 for d in distances if d <= 100)
        within_500 = sum(1 for d in distances if d <= 500)
        median_dist = sorted(distances)[len(distances) // 2]
        avg_dist = sum(distances) / len(distances)

        print(f"GeoCLIP results (on {len(geoclip_with_gps)} images with GPS ground truth):")
        print(f"  Within 25 km:   {within_25}/{len(geoclip_with_gps)} ({within_25/len(geoclip_with_gps)*100:.0f}%)")
        print(f"  Within 100 km:  {within_100}/{len(geoclip_with_gps)} ({within_100/len(geoclip_with_gps)*100:.0f}%)")
        print(f"  Within 500 km:  {within_500}/{len(geoclip_with_gps)} ({within_500/len(geoclip_with_gps)*100:.0f}%)")
        print(f"  Median distance: {median_dist:.0f} km")
        print(f"  Average distance: {avg_dist:.0f} km")

        country_matches = [r for r in geoclip_results if r["country_match"] is True]
        print(f"  Country match: {len(country_matches)}/{len(geoclip_results)} ({len(country_matches)/len(geoclip_results)*100:.0f}%)")
    else:
        print("No GeoCLIP results to analyze.")

    print(f"\n  Time: {elapsed:.0f}s ({elapsed/n:.1f}s per image)")

    # Detailed results table
    print(f"\n{'='*70}")
    print("DETAILED RESULTS")
    print(f"{'='*70}\n")
    print(f"{'#':>3} {'Filter':>10} {'GT Location':<35} {'Pred Location':<35} {'Dist':>8}")
    print("-" * 95)
    for i, r in enumerate(results):
        gt_str = f"{r.get('gt_country', '?')}, {r.get('gt_city', '?')}"[:33]
        if r["geoclip_ran"]:
            pred_str = f"{r.get('pred_country', '?')}, {r.get('pred_city', '?')}"[:33]
            dist_str = f"{r['distance_km']:.0f}km" if r["distance_km"] is not None else "?"
        else:
            pred_str = "(skipped)"
            dist_str = "-"
        filter_str = "landmark" if r["is_landmark"] else ("not LM" if r["is_landmark"] is False else "err")
        print(f"{i+1:3d} {filter_str:>10} {gt_str:<35} {pred_str:<35} {dist_str:>8}")

    # Show landmark classifications
    if not args.skip_filter:
        print(f"\n--- Images classified as landmarks ---")
        for r in results:
            if r["is_landmark"]:
                print(f"  {r['file']}")
                print(f"    Reason: {r['filter_reason']}")
                if r["geoclip_ran"] and r["distance_km"] is not None:
                    print(f"    GeoCLIP: {r['pred_country']}, {r['pred_city']} ({r['distance_km']:.0f}km, p={r['pred_prob']:.2f})")
                print()


if __name__ == "__main__":
    main()
