"""Publish preferred picks into the picks root (the Immich external library).

The picks root mirrors the album layout (``<picks_root>/<Albumnaam>/``) with
ONE file per source image, named after the source stem (variant suffix
dropped).  Re-picking a different variant replaces the same path, so Immich
sees an updated file — never a duplicate.

Files are hardlinked from the enhanced root when possible (same volume, zero
extra disk usage), falling back to a copy.
"""
from __future__ import annotations

import json
import logging
import re
import shutil
from pathlib import Path
from typing import NamedTuple

logger = logging.getLogger(__name__)

_ALBUM_NAME_RE = re.compile(r"(?im)^albumnaam\s*:\s*(.+)$")


class PublishResult(NamedTuple):
    published: list[str]     # pick paths written/updated
    removed: list[str]       # pick paths deleted (pick cleared or source gone)
    skipped: list[str]       # images with no pick yet
    errors: list[str]       # (path, message) tuples as strings


def _album_for_folder(folder: Path) -> str:
    """Derive the album name from the folder's description.txt (Albumnaam)."""
    desc = folder / "description.txt"
    if desc.exists():
        m = _ALBUM_NAME_RE.search(desc.read_text(encoding="utf-8"))
        if m and m.group(1).strip():
            return m.group(1).strip()
    return folder.name


def _link_or_copy(src: Path, dst: Path) -> None:
    """Hardlink *src* to *dst* when possible, else copy."""
    try:
        dst.unlink(missing_ok=True)
        dst.hardlink_to(src)
    except OSError:
        # different filesystem or unsupported — fall back to copying
        shutil.copy2(src, dst)


def publish_folder(
    source_folder: Path,
    enhanced_root: Path,
    picks_root: Path,
    dry_run: bool = False,
) -> PublishResult:
    """Publish the picks of one source folder into the picks root.

    For every image in *source_folder*:
      - with a ``preferred_variant`` in its analysis JSON → its
        ``preferred_path`` is linked to ``<picks_root>/<album>/<stem>.jpg``
      - without a pick → nothing (skipped)
      - a previously published pick that no longer exists (pick cleared or
        source image removed) is removed from the picks root

    Returns counts and lists for reporting.
    """
    source_folder = Path(source_folder)
    enhanced_root = Path(enhanced_root)
    picks_root = Path(picks_root)

    album = _album_for_folder(source_folder)
    out_dir = enhanced_root / album
    album_picks_dir = picks_root / album

    published: list[str] = []
    removed: list[str] = []
    skipped: list[str] = []
    errors: list[str] = []

    # Existing published picks (to detect stale ones)
    existing_picks: set[str] = set()
    if album_picks_dir.is_dir():
        existing_picks = {p.name for p in album_picks_dir.iterdir() if p.is_file()}

    # Walk the source images
    from ..config.defaults import DEFAULT_SUPPORTED_FORMATS

    published_stems: set[str] = set()
    errored_stems: set[str] = set()
    for f in sorted(source_folder.iterdir()):
        if not f.is_file() or f.suffix.lower() not in DEFAULT_SUPPORTED_FORMATS:
            continue

        jf = out_dir / f"{f.stem}_analyzed.json"
        if not jf.is_file():
            skipped.append(f.name)
            continue
        try:
            data = json.loads(jf.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            errors.append(f"{f.name}: cannot read analysis JSON ({exc})")
            errored_stems.add(f.stem)
            continue

        preferred_path = data.get("preferred_path")
        if not preferred_path or not Path(preferred_path).is_file():
            skipped.append(f.name)
            continue

        dst = album_picks_dir / f"{f.stem}.jpg"
        if not dry_run:
            album_picks_dir.mkdir(parents=True, exist_ok=True)
            try:
                _link_or_copy(Path(preferred_path), dst)
            except OSError as exc:
                errors.append(f"{f.name}: cannot publish ({exc})")
                errored_stems.add(f.stem)
                continue
        published.append(str(dst))
        published_stems.add(f.stem)

    # Stale picks: published files that were not re-published this run —
    # either the pick was cleared or the source image is gone. Picks for
    # images with errors are kept (their state is unknown, not "no pick").
    for name in sorted(existing_picks):
        stem = name[:-len(".jpg")] if name.lower().endswith(".jpg") else name
        if stem in published_stems or stem in errored_stems:
            continue
        target = album_picks_dir / name
        if not dry_run:
            try:
                target.unlink(missing_ok=True)
            except OSError as exc:
                errors.append(f"{name}: cannot remove stale pick ({exc})")
                continue
        removed.append(str(target))

    # Clean up empty album dirs (Immich dislikes empty library folders)
    if not dry_run and album_picks_dir.is_dir() and not any(album_picks_dir.iterdir()):
        try:
            album_picks_dir.rmdir()
        except OSError:
            pass

    return PublishResult(published, removed, skipped, errors)


def publish_all(
    photos_root: Path,
    enhanced_root: Path,
    picks_root: Path,
    dry_run: bool = False,
) -> dict[str, PublishResult]:
    """Publish picks for every folder under *photos_root*."""
    results: dict[str, PublishResult] = {}
    for folder in sorted(Path(photos_root).iterdir()):
        if not folder.is_dir() or folder.name.startswith("."):
            continue
        results[folder.name] = publish_folder(folder, enhanced_root, picks_root, dry_run)
    return results
