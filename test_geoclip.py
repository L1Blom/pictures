#!/usr/bin/env python3
"""Test GeoCLIP location detection on 50 random images from ~/enhanced.

GeoCLIP predicts GPS coordinates directly from an image (no text/LLM needed).
This script compares its predictions against the ground truth locations
stored in the existing _analyzed.json files (from description.txt or prior LLM runs).

Usage:
    python3 test_geoclip.py                  # test 50 random images
    python3 test_geoclip.py --sample 20      # test 20 images
    python3 test_geoclip.py --seed 42        # reproducible selection
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path

ENHANCED_ROOT = Path.home() / "enhanced"


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


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance between two GPS points in km."""
    import math
    R = 6371  # Earth radius in km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    )
    return 2 * R * math.asin(math.sqrt(a))


def reverse_geocode(lat: float, lon: float) -> dict:
    """Use Nominatim to reverse-geocode GPS to place names."""
    import requests
    import time as _time

    _time.sleep(1.1)  # Nominatim rate limit: 1 request/second
    try:
        resp = requests.get(
            "https://nominatim.openstreetmap.org/reverse",
            params={
                "lat": lat,
                "lon": lon,
                "format": "json",
                "addressdetails": 1,
                "zoom": 10,
            },
            headers={"User-Agent": "picture-analyzer-geoclip-test/1.0"},
            timeout=10,
        )
        data = resp.json()
        addr = data.get("address", {})
        return {
            "country": addr.get("country", ""),
            "region": addr.get("state", addr.get("county", "")),
            "city_or_area": addr.get("city", addr.get("town", addr.get("village", addr.get("hamlet", "")))),
            "display_name": data.get("display_name", ""),
        }
    except Exception as e:
        return {"country": "", "region": "", "city_or_area": "", "display_name": f"ERROR: {e}"}


def normalize(s: str) -> str:
    return s.strip().lower().replace("-", " ").replace(",", "")


def fuzzy_match(pred: str, gt: str) -> bool:
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


def main():
    parser = argparse.ArgumentParser(description="Test GeoCLIP location detection")
    parser.add_argument("--sample", type=int, default=50, help="Number of images to test")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--no-reverse-geocode", action="store_true",
                        help="Skip Nominatim reverse geocoding (faster, GPS-only comparison)")
    args = parser.parse_args()

    random.seed(args.seed)

    print(f"Finding {args.sample} random images with ground truth in {ENHANCED_ROOT}...")
    samples = find_sample_images(ENHANCED_ROOT, args.sample)
    print(f"Selected {len(samples)} images.\n")

    # Print ground truth
    print("Ground truth locations:")
    for i, (jpg, gt) in enumerate(samples):
        loc = gt["loc"]
        gps = gt["gps"]
        gps_str = f" ({gps.get('latitude', '?'):.4f}, {gps.get('longitude', '?'):.4f})" if gps.get("latitude") else " (no GPS)"
        print(f"  [{i+1:2d}] {jpg.parent.name}/{jpg.name}")
        print(f"       -> {loc.get('country', '?')}, {loc.get('region', '?')}, {loc.get('city_or_area', '?')}{gps_str}")
    print()

    # Load GeoCLIP
    print("Loading GeoCLIP model...")
    try:
        from geoclip import GeoCLIP
        model = GeoCLIP()
        print("GeoCLIP loaded.\n")
    except ImportError:
        print("ERROR: geoclip not installed. Install with: pip install geoclip")
        sys.exit(1)
    except Exception as e:
        print(f"ERROR loading GeoCLIP: {e}")
        print("Install with: pip install geoclip")
        sys.exit(1)

    # Run predictions
    results = []
    start_time = time.time()

    for i, (jpg, gt) in enumerate(samples):
        rel = f"{jpg.parent.name}/{jpg.name}"
        print(f"  [{i+1}/{len(samples)}] {rel}...", end=" ", flush=True)

        try:
            # GeoCLIP prediction
            top_gps, top_prob = model.predict(str(jpg), top_k=5)
            pred_lat, pred_lon = float(top_gps[0][0]), float(top_gps[0][1])
            pred_prob = float(top_prob[0])

            # Compare with ground truth GPS if available
            gt_gps = gt.get("gps", {})
            gt_lat = gt_gps.get("latitude")
            gt_lon = gt_gps.get("longitude")

            distance_km = None
            if gt_lat and gt_lon:
                distance_km = haversine_km(gt_lat, gt_lon, pred_lat, pred_lon)

            # Reverse geocode to get place names (unless skipped)
            pred_place = {}
            if not args.no_reverse_geocode:
                pred_place = reverse_geocode(pred_lat, pred_lon)

            # Compare place names
            gt_loc = gt["loc"]
            country_match = fuzzy_match(pred_place.get("country", ""), gt_loc.get("country", "")) if pred_place else None
            city_match = fuzzy_match(pred_place.get("city_or_area", ""), gt_loc.get("city_or_area", "")) if pred_place else None

            result = {
                "file": rel,
                "gt_country": gt_loc.get("country", ""),
                "gt_region": gt_loc.get("region", ""),
                "gt_city": gt_loc.get("city_or_area", ""),
                "gt_lat": gt_lat,
                "gt_lon": gt_lon,
                "pred_lat": pred_lat,
                "pred_lon": pred_lon,
                "pred_prob": pred_prob,
                "pred_country": pred_place.get("country", ""),
                "pred_city": pred_place.get("city_or_area", ""),
                "distance_km": distance_km,
                "country_match": country_match,
                "city_match": city_match,
            }
            results.append(result)

            # Print result
            dist_str = f" ({distance_km:.0f}km)" if distance_km is not None else ""
            place_str = f" {pred_place.get('country', '?')}, {pred_place.get('city_or_area', '?')}" if pred_place else ""
            print(f"-> {pred_lat:.4f}, {pred_lon:.4f} (p={pred_prob:.2f}){place_str}{dist_str}")

        except Exception as e:
            print(f"ERROR: {e}")
            results.append({
                "file": rel,
                "gt_country": gt["loc"].get("country", ""),
                "gt_city": gt["loc"].get("city_or_area", ""),
                "pred_lat": None,
                "pred_lon": None,
                "pred_prob": 0,
                "distance_km": None,
                "country_match": None,
                "city_match": None,
                "error": str(e),
            })

    elapsed = time.time() - start_time

    # --- Summary ---
    print(f"\n\n{'='*70}")
    print("SUMMARY")
    print(f"{'='*70}\n")

    n = len(results)

    # GPS distance stats
    distances = [r["distance_km"] for r in results if r["distance_km"] is not None]
    if distances:
        within_1km = sum(1 for d in distances if d <= 1)
        within_25km = sum(1 for d in distances if d <= 25)
        within_100km = sum(1 for d in distances if d <= 100)
        within_500km = sum(1 for d in distances if d <= 500)
        median_dist = sorted(distances)[len(distances) // 2]
        avg_dist = sum(distances) / len(distances)

        print(f"GPS Distance (n={len(distances)} with ground truth GPS):")
        print(f"  Within 1 km:    {within_1km}/{len(distances)} ({within_1km/len(distances)*100:.0f}%)")
        print(f"  Within 25 km:   {within_25km}/{len(distances)} ({within_25km/len(distances)*100:.0f}%)")
        print(f"  Within 100 km:  {within_100km}/{len(distances)} ({within_100km/len(distances)*100:.0f}%)")
        print(f"  Within 500 km:  {within_500km}/{len(distances)} ({within_500km/len(distances)*100:.0f}%)")
        print(f"  Median distance: {median_dist:.0f} km")
        print(f"  Average distance: {avg_dist:.0f} km")
        print()

    # Place name match stats
    country_matches = [r for r in results if r.get("country_match") is not None]
    city_matches = [r for r in results if r.get("city_match") is not None]
    if country_matches:
        cm = sum(1 for r in country_matches if r["country_match"])
        print(f"Country match (reverse-geocoded): {cm}/{len(country_matches)} ({cm/len(country_matches)*100:.0f}%)")
    if city_matches:
        cm = sum(1 for r in city_matches if r["city_match"])
        print(f"City match (reverse-geocoded):    {cm}/{len(city_matches)} ({cm/len(city_matches)*100:.0f}%)")

    print(f"\nTime: {elapsed:.0f}s ({elapsed/n:.1f}s per image)")
    print(f"Model: GeoCLIP (CLIP + GPS alignment, trained on 4.7M images)")

    # Print detailed results
    print(f"\n{'='*70}")
    print("DETAILED RESULTS")
    print(f"{'='*70}\n")
    print(f"{'#':>3} {'GT Location':<40} {'Pred Location':<40} {'Dist':>8} {'Prob':>6}")
    print("-" * 100)
    for i, r in enumerate(results):
        gt_str = f"{r.get('gt_country', '?')}, {r.get('gt_city', '?')}"[:38]
        pred_str = f"{r.get('pred_country', '?')}, {r.get('pred_city', '?')}"[:38]
        dist_str = f"{r['distance_km']:.0f}km" if r.get("distance_km") is not None else "?"
        prob_str = f"{r.get('pred_prob', 0):.2f}"
        print(f"{i+1:3d} {gt_str:<40} {pred_str:<40} {dist_str:>8} {prob_str:>6}")

    # Print worst predictions
    print(f"\n--- Worst 10 predictions (by distance) ---")
    sorted_by_dist = sorted(results, key=lambda r: r.get("distance_km") or 0, reverse=True)
    for r in sorted_by_dist[:10]:
        print(f"  {r['file']}")
        gt_lat = r.get('gt_lat')
        gt_lon = r.get('gt_lon')
        pred_lat = r.get('pred_lat')
        pred_lon = r.get('pred_lon')
        gt_gps = f"({gt_lat:.4f}, {gt_lon:.4f})" if isinstance(gt_lat, (int, float)) and isinstance(gt_lon, (int, float)) else "(no GPS)"
        pred_gps = f"({pred_lat:.4f}, {pred_lon:.4f})" if isinstance(pred_lat, (int, float)) and isinstance(pred_lon, (int, float)) else "(no pred)"
        print(f"    GT:   {r.get('gt_country', '?')}, {r.get('gt_city', '?')} {gt_gps}")
        print(f"    Pred: {r.get('pred_country', '?')}, {r.get('pred_city', '?')} {pred_gps}")
        print(f"    Dist: {r.get('distance_km', 0):.0f}km, Prob: {r.get('pred_prob', 0):.2f}")
        print()


if __name__ == "__main__":
    main()
