"""Slide/dia restoration using typed profiles.

Replaces the legacy ``SlideRestoration`` class with a version that uses
the Phase 1 Pydantic models (``SlideProfile``, ``ColorBalance``) and
centralized defaults from ``defaults.py``.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from PIL import Image, ImageEnhance, ImageFilter

from ...config.defaults import DEFAULT_JPEG_QUALITY, DEFAULT_SLIDE_PROFILES
from ...core.models import ColorBalance, SlideProfile, SlideProfileDetection


def _load_builtin_profiles() -> dict[str, SlideProfile]:
    """Convert the raw dict profiles from defaults.py into typed models."""
    profiles = {}
    for key, raw in DEFAULT_SLIDE_PROFILES.items():
        cb_raw = raw.get("color_balance", {})
        profiles[key] = SlideProfile(
            name=raw.get("name", key),
            description=raw.get("description", ""),
            saturation=raw.get("saturation", 1.0),
            contrast=raw.get("contrast", 1.0),
            brightness=raw.get("brightness", 1.0),
            sharpness=raw.get("sharpness", 1.0),
            color_balance=ColorBalance(
                red=cb_raw.get("red", 1.0),
                green=cb_raw.get("green", 1.0),
                blue=cb_raw.get("blue", 1.0),
            ),
            denoise=raw.get("denoise", False),
            denoise_radius=raw.get("denoise_radius", 0.5),
        )
    return profiles


# Module-level cache of typed profiles
BUILTIN_PROFILES: dict[str, SlideProfile] = _load_builtin_profiles()


class SlideRestorer:
    """Restore scanned slides using typed ``SlideProfile`` models.

    Usage::

        restorer = SlideRestorer()
        result_path = restorer.restore("scan.jpg", "faded", "restored.jpg")

    The restorer can also auto-detect the best profile from AI analysis::

        result_path = restorer.auto_restore("scan.jpg", analysis_result, "restored.jpg")
    """

    def __init__(
        self,
        profiles: dict[str, SlideProfile] | None = None,
        jpeg_quality: int = DEFAULT_JPEG_QUALITY,
    ):
        self._profiles = profiles or dict(BUILTIN_PROFILES)
        self.jpeg_quality = jpeg_quality

    @property
    def available_profiles(self) -> list[str]:
        """Names of all available restoration profiles."""
        return sorted(self._profiles.keys())

    def get_profile(self, name: str) -> SlideProfile | None:
        """Look up a profile by name."""
        return self._profiles.get(name)

    def add_profile(self, name: str, profile: SlideProfile) -> None:
        """Register a custom profile."""
        self._profiles[name] = profile

    # ── Restore ──────────────────────────────────────────────────────

    def restore(
        self,
        image_path: str | Path,
        profile_name: str = "aged",
        output_path: str | Path | None = None,
        denoise: bool = True,
        despeckle: bool = True,
    ) -> str | None:
        """Apply a named restoration profile to a scanned slide.

        Args:
            image_path: Source image path.
            profile_name: Name of the restoration profile.
            output_path: Where to save the result.
            denoise: Apply noise reduction.
            despeckle: Apply median filter for dust/speckle removal.

        Returns:
            Path to restored image, or None on failure.
        """
        profile = self._profiles.get(profile_name)
        if not profile:
            print(f"Unknown profile: {profile_name}. Using 'aged'")
            profile = self._profiles["aged"]
            profile_name = "aged"

        try:
            image = Image.open(str(image_path))
            if image.mode != "RGB":
                image = image.convert("RGB")

            print(f"\nRestoring slide with '{profile_name}' profile:")
            print(f"  Description: {profile.description}")

            # 1. Optional despeckle
            if despeckle:
                print("  → Removing dust and speckles...")
                image = image.filter(ImageFilter.MedianFilter(size=3))

            # 2. Color balance
            cb = profile.color_balance
            if (cb.red, cb.green, cb.blue) != (1.0, 1.0, 1.0):
                print("  → Correcting color balance...")
                r, g, b = image.split()
                r = ImageEnhance.Brightness(r).enhance(cb.red)
                g = ImageEnhance.Brightness(g).enhance(cb.green)
                b = ImageEnhance.Brightness(b).enhance(cb.blue)
                image = Image.merge("RGB", (r, g, b))

            # 3. Brightness
            print(f"  → Adjusting brightness ({profile.brightness:.2f}x)...")
            image = ImageEnhance.Brightness(image).enhance(profile.brightness)

            # 4. Contrast
            print(f"  → Restoring contrast ({profile.contrast:.2f}x)...")
            image = ImageEnhance.Contrast(image).enhance(profile.contrast)

            # 5. Saturation
            print(f"  → Restoring color saturation ({profile.saturation:.2f}x)...")
            image = ImageEnhance.Color(image).enhance(profile.saturation)

            # 6. Optional denoise
            if denoise and profile.denoise:
                print("  → Reducing film grain and noise...")
                image = image.filter(ImageFilter.GaussianBlur(radius=profile.denoise_radius))

            # 7. Sharpness
            print(f"  → Enhancing sharpness ({profile.sharpness:.2f}x)...")
            image = ImageEnhance.Sharpness(image).enhance(profile.sharpness)

            # Save
            out = str(output_path or image_path)
            image.save(out, "JPEG", quality=self.jpeg_quality)
            print(f"\n✓ Slide restoration complete: {out}")
            return out

        except Exception as e:
            print(f"✗ Error during slide restoration: {e}")
            return None

    # ── Auto-detect ──────────────────────────────────────────────────

    def auto_restore(
        self,
        image_path: str | Path,
        analysis_data: dict[str, Any] | None = None,
        analysis_result: "AnalysisResult | None" = None,
        output_path: str | Path | None = None,
    ) -> str | None:
        """Auto-detect the best profile and restore.

        Checks the AI-provided ``slide_profiles`` list first, then falls
        back to heuristic detection from the enhancement data.

        Args:
            image_path: Source image path.
            analysis_data: Legacy analysis dict (backward compat).
            analysis_result: Typed AnalysisResult (preferred).
            output_path: Where to save.

        Returns:
            Path to restored image, or None on failure.
        """
        profile_name = "aged"  # default

        # Prefer typed AnalysisResult
        if analysis_result and analysis_result.slide_profile:
            sp = analysis_result.slide_profile
            profile_name = sp.profile_name
            print(f"\nUsing AI-provided slide profile:")
            print(f"  Profile: {profile_name}")
            print(f"  Confidence: {sp.confidence}%")
        elif analysis_data:
            # Legacy dict path
            ai_profiles = analysis_data.get("slide_profiles", [])
            if ai_profiles and isinstance(ai_profiles, list):
                best = ai_profiles[0]
                if isinstance(best, dict):
                    profile_name = best.get("profile", "aged")
                    confidence = best.get("confidence", 0)
                    print(f"\nUsing AI-provided slide profile:")
                    print(f"  Profile: {profile_name}")
                    print(f"  Confidence: {confidence}%")
            else:
                # Heuristic fallback
                assessment = self._heuristic_assess(analysis_data)
                profile_name = assessment.get("recommended_profile", "aged")
                print(f"\nNo AI slide profile provided, using heuristic analysis:")
                print(f"  Condition: {assessment.get('condition', 'unknown')}")
                print(f"  Recommended: {profile_name}")

        print(f"\nApplying restoration profile: {profile_name}")
        return self.restore(image_path, profile_name, output_path)

    # ── Heuristic assessment (ported from legacy) ────────────────────

    def _heuristic_assess(self, analysis_data: dict[str, Any]) -> dict[str, Any]:
        """Assess slide condition from enhancement data heuristically."""
        assessment: dict[str, Any] = {
            "condition": "unknown",
            "confidence": 0.0,
            "characteristics": [],
            "recommended_profile": "aged",
        }

        enhancement = analysis_data.get("enhancement", {})
        if not isinstance(enhancement, dict):
            return assessment

        color_info = enhancement.get("color_analysis", {})
        if isinstance(color_info, dict):
            combined = str(color_info.get("color_temperature", "")).lower()
            combined += str(color_info.get("detected_color_casts", "")).lower()

            if any(w in combined for w in ("magenta", "red", "reddish")):
                assessment["characteristics"].append("red_cast")
                assessment["recommended_profile"] = "red_cast"
            elif any(w in combined for w in ("yellow", "warm", "sepia", "golden")):
                assessment["characteristics"].append("yellow_cast")
                assessment["recommended_profile"] = "yellow_cast"
            elif any(w in combined for w in ("cyan", "cool", "blue")):
                assessment["characteristics"].append("cool_cast")
                assessment["recommended_profile"] = "color_cast"

            sat = str(color_info.get("saturation_level", "")).lower()
            if any(w in sat for w in ("dull", "low", "muted", "faded", "washed")):
                assessment["characteristics"].append("faded")
                if "recommended_profile" == "aged":
                    assessment["recommended_profile"] = "faded"

        if len(assessment["characteristics"]) >= 3:
            assessment["condition"] = "heavily_aged"
        elif assessment["characteristics"]:
            assessment["condition"] = assessment["characteristics"][0]
        else:
            assessment["condition"] = "well_preserved"
            assessment["recommended_profile"] = "well_preserved"

        return assessment
